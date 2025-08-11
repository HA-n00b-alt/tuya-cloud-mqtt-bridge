#!/usr/bin/env python3
import os
import time
import json
import hmac
import hashlib
import secrets
from urllib.parse import urlencode

import requests
import paho.mqtt.client as paho

# ---------- Minimal Tuya OpenAPI (v2 signature) ----------
class TuyaOpenAPI:
    """
    Tuya OpenAPI client using v2 signing:
      stringToSign = METHOD + "\n" + SHA256(body) + "\n" + headersPart + "\n" + pathWithQuery
      message      = client_id + [access_token] + t + nonce + stringToSign
      sign         = HMAC-SHA256(ACCESS_KEY, message).hexdigest().upper()
    """
    def __init__(self, base_url, access_id, access_key, logger=None):
        self.base_url = base_url.rstrip('/')
        self.access_id = access_id
        self.access_key = access_key
        self.access_token = None
        self.log = logger or (lambda *a, **k: None)

    def connect(self):
        data = self._request('GET', '/v1.0/token', params={'grant_type': 1}, use_token=False)
        if isinstance(data, dict) and data.get('success'):
            tok = data.get('result', {}).get('access_token')
            if tok:
                self.access_token = tok
                self.log(f"Tuya token obtained; expires in {data.get('result',{}).get('expire_time')}s.")
        return data

    def get(self, path, params=None):
        return self._request('GET', path, params=params, use_token=True)

    def _request(self, method, path, params=None, body=None, use_token=True, retry=True):
        method = method.upper()
        if not path.startswith('/'):
            path = '/' + path

        qs = urlencode(sorted([(k, str(v)) for k, v in (params or {}).items()])) if params else ''
        full_path = f"{path}?{qs}" if qs else path

        body_str = '' if (method == 'GET' or body is None) else json.dumps(body, separators=(',', ':'), ensure_ascii=False)
        content_sha256 = hashlib.sha256(body_str.encode('utf-8')).hexdigest()

        string_to_sign = f"{method}\n{content_sha256}\n\n{full_path}"

        t = str(int(time.time() * 1000))
        nonce = secrets.token_hex(16)

        if use_token and self.access_token:
            message = self.access_id + self.access_token + t + nonce + string_to_sign
        else:
            message = self.access_id + t + nonce + string_to_sign

        sign = hmac.new(self.access_key.encode('utf-8'),
                        msg=message.encode('utf-8'),
                        digestmod=hashlib.sha256).hexdigest().upper()

        headers = {
            'client_id': self.access_id,
            'sign': sign,
            't': t,
            'nonce': nonce,
            'sign_method': 'HMAC-SHA256',
        }
        if use_token and self.access_token:
            headers['access_token'] = self.access_token
        if body_str:
            headers['Content-Type'] = 'application/json'

        url = self.base_url + full_path
        try:
            resp = requests.get(url, headers=headers, timeout=15)
        except Exception as e:
            return {'success': False, 'code': 0, 'msg': f'HTTP error: {e}'}

        try:
            data = resp.json()
        except Exception:
            data = {'success': False, 'code': resp.status_code, 'msg': 'non-json', 'text': resp.text}

        # Auto-refresh once on 1010
        if use_token and isinstance(data, dict) and data.get('code') == 1010 and retry:
            self.log("Token invalid; refreshing…")
            c = self.connect()
            if isinstance(c, dict) and c.get('success'):
                return self._request(method, path, params=params, body=body, use_token=True, retry=False)

        return data

# ---------- Env/config ----------
ACCESS_ID      = os.environ["ACCESS_ID"]
ACCESS_KEY     = os.environ["ACCESS_KEY"]
REGION         = os.environ.get("REGION","eu")
USERNAME       = os.environ.get("USERNAME","")
COUNTRY_CODE   = os.environ.get("COUNTRY_CODE","39")
APP_SCHEMA     = os.environ.get("APP_SCHEMA","smartlife")
DEVICE_ID      = os.environ["DEVICE_ID"]
ENTITY_ID      = os.environ.get("ENTITY_ID","tuya_sensor")
NAME           = os.environ.get("NAME","Tuya Sensor")
DEVICE_CLASS   = os.environ.get("DEVICE_CLASS","opening")
POLL_INTERVAL  = int(os.environ.get("POLL_INTERVAL","20"))
MQTT_HOST      = os.environ.get("MQTT_HOST","core-mosquitto")
MQTT_PORT      = int(os.environ.get("MQTT_PORT","1883"))
MQTT_USER      = os.environ.get("MQTT_USER","")
MQTT_PASSWORD  = os.environ.get("MQTT_PASSWORD","")
DPS_ACTIVE     = os.environ.get("DPS_ACTIVE")    # not used for v2 codes but kept for compatibility
DPS_BATTERY    = os.environ.get("DPS_BATTERY")

OFFLINE_AFTER  = 300  # seconds without a successful API read → mark entities unavailable

REGION_HOSTS = {
    "eu": "https://openapi.tuyaeu.com",
    "us": "https://openapi.tuyaus.com",
    "cn": "https://openapi.tuyacn.com",
    "in": "https://openapi.tuyain.com",
}
BASE_URL = REGION_HOSTS.get(REGION, REGION_HOSTS["eu"])

def log(msg: str):
    ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{ts} {msg}", flush=True)

# ---------- MQTT ----------
AVAIL_TOPIC = f"tuya/{ENTITY_ID}/availability"
STATE_TOPIC = f"tuya/{ENTITY_ID}/state"
BATT_TOPIC  = f"tuya/{ENTITY_ID}/battery"

def mqtt_connect():
    client = paho.Client(client_id=f"tuya-bridge-{ENTITY_ID}", clean_session=True)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD or None)
    client.will_set(AVAIL_TOPIC, "offline", retain=True)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    log(f"Connecting to MQTT broker at {MQTT_HOST}:{MQTT_PORT}…")
    return client

def publish_discovery(mqtt):
    cfg = {
        "name": NAME,
        "unique_id": f"{ENTITY_ID}",
        "state_topic": STATE_TOPIC,
        "availability_topic": AVAIL_TOPIC,
        "device_class": DEVICE_CLASS,
        "payload_on": "ON",
        "payload_off": "OFF",
        "device": {"identifiers":[DEVICE_ID], "manufacturer":"Tuya","name":NAME,"model":"Cloud"},
    }
    mqtt.publish(f"homeassistant/binary_sensor/{ENTITY_ID}/config", json.dumps(cfg), retain=True)

    batt_cfg = {
        "name": f"{NAME} Battery",
        "unique_id": f"{ENTITY_ID}_battery",
        "state_topic": BATT_TOPIC,
        "availability_topic": AVAIL_TOPIC,
        "unit_of_measurement": "%",
        "device_class": "battery",
        "entity_category": "diagnostic",
        "device":{"identifiers":[DEVICE_ID]}
    }
    mqtt.publish(f"homeassistant/sensor/{ENTITY_ID}_battery/config", json.dumps(batt_cfg), retain=True)
    log("Published MQTT discovery config.")

# ---------- v2 shadow fetch ----------
def fetch_shadow_v2(api: TuyaOpenAPI):
    sh = api.get(f"/v2.0/cloud/thing/{DEVICE_ID}/shadow/properties")
    log(f"OpenAPI v2 shadow response: {json.dumps(sh, ensure_ascii=False)}")
    if isinstance(sh, dict) and sh.get("success"):
        props = sh.get("result", {}).get("properties", [])
        by_code = {}
        if isinstance(props, list):
            for item in props:
                code = item.get("code"); val = item.get("value")
                if code is not None:
                    by_code[code] = val
        elif isinstance(props, dict):
            by_code = props
        if by_code:
            return by_code
    return {}

# ---------- value pickers ----------
def pick_boolean(by_code):
    # Prefer explicit door/contact codes; fall back to common names
    for k in ["doorcontact_state","contact_state","contact","door","open","switch_1","switch"]:
        if k in by_code and isinstance(by_code[k], (bool, int)):
            return bool(by_code[k])
    return None

def pick_battery(by_code):
    if "battery_percentage" in by_code and isinstance(by_code["battery_percentage"], (int,float)):
        return int(by_code["battery_percentage"])
    if "battery" in by_code and isinstance(by_code["battery"], (int,float)):
        return int(by_code["battery"])
    if "battery_state" in by_code and isinstance(by_code["battery_state"], str):
        m = {"low": 20, "middle": 60, "medium": 60, "high": 100}
        return m.get(by_code["battery_state"].strip().lower())
    return None

# ---------- main ----------
def main():
    log(f"Starting Tuya Cloud → MQTT bridge for device {DEVICE_ID} ({NAME}), polling every {POLL_INTERVAL}s.")
    log("Configuration:")
    log(f"  Region: {REGION}")
    log(f"  Base URL: {BASE_URL}")
    log(f"  Username: {USERNAME[:3]}***")
    log(f"  Country Code: {COUNTRY_CODE}")
    log(f"  App Schema: {APP_SCHEMA}")
    log(f"  Access ID: {ACCESS_ID[:8]}***")
    log(f"  Device ID: {DEVICE_ID}")

    mqtt = mqtt_connect()
    publish_discovery(mqtt)
    # Start as online; will flip to offline if no success for > OFFLINE_AFTER
    mqtt.publish(AVAIL_TOPIC, "online", retain=True)

    api = TuyaOpenAPI(BASE_URL, ACCESS_ID, ACCESS_KEY, logger=log)
    log(f"Connecting Tuya OpenAPI at {BASE_URL} with schema={APP_SCHEMA}, country={COUNTRY_CODE} …")
    try:
        response = api.connect()
        log(f"OpenAPI connect response: {response}")
    except Exception as e:
        log(f"OpenAPI connect exception: {e}")

    last_ok = time.time()  # track last successful API read
    avail_state = "online"

    while True:
        try:
            by_code = fetch_shadow_v2(api)
            if by_code:
                # got data → ensure availability is online
                now = time.time()
                last_ok = now
                if avail_state != "online":
                    mqtt.publish(AVAIL_TOPIC, "online", retain=True)
                    avail_state = "online"
                    log("Availability → online (API read succeeded).")

                onoff = pick_boolean(by_code)
                batt  = pick_battery(by_code)

                if onoff is not None:
                    mqtt.publish(STATE_TOPIC, "ON" if onoff else "OFF", retain=True)
                    log(f"State updated (openapi-v2): {'ON' if onoff else 'OFF'}")
                else:
                    log("State key not found in v2 shadow (will retry).")

                if batt is not None:
                    mqtt.publish(BATT_TOPIC, str(batt), retain=True)
                    log(f"Battery updated (openapi-v2): {batt}%")
            else:
                # No data — check availability timeout
                if time.time() - last_ok > OFFLINE_AFTER and avail_state != "offline":
                    mqtt.publish(AVAIL_TOPIC, "offline", retain=True)
                    avail_state = "offline"
                    log(f"No successful API read for > {OFFLINE_AFTER}s → Availability → offline.")

        except Exception as e:
            log(f"[ERROR] {e}")
            import traceback
            log(f"[TRACEBACK] {traceback.format_exc()}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
