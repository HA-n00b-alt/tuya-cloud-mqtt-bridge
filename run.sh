#!/usr/bin/env bash
set -euo pipefail

OPTS=/data/options.json

ACCESS_ID=$(jq -r '.access_id' "$OPTS")
ACCESS_KEY=$(jq -r '.access_key' "$OPTS")
REGION=$(jq -r '.region // "eu"' "$OPTS")
USERNAME=$(jq -r '.username // ""' "$OPTS")
PASSWORD=$(jq -r '.password // ""' "$OPTS")
COUNTRY_CODE=$(jq -r '.country_code // "39"' "$OPTS")
APP_SCHEMA=$(jq -r '.app_schema // "smartlife"' "$OPTS")
DEVICE_ID=$(jq -r '.device_id' "$OPTS")
ENTITY_ID=$(jq -r '.entity_id // "tuya_sensor"' "$OPTS")
NAME=$(jq -r '.name // "Tuya Sensor"' "$OPTS")
DEVICE_CLASS=$(jq -r '.device_class // "motion"' "$OPTS")
POLL_INTERVAL=$(jq -r '.poll_interval // 20' "$OPTS")
MQTT_HOST=$(jq -r '.mqtt_host // "core-mosquitto"' "$OPTS")
MQTT_PORT=$(jq -r '.mqtt_port // 1883' "$OPTS")
MQTT_USER=$(jq -r '.mqtt_user // ""' "$OPTS")
MQTT_PASSWORD=$(jq -r '.mqtt_password // ""' "$OPTS")
DPS_ACTIVE=$(jq -r '.dps_active // empty' "$OPTS")
DPS_BATTERY=$(jq -r '.dps_battery // empty' "$OPTS")

export ACCESS_ID ACCESS_KEY REGION USERNAME PASSWORD COUNTRY_CODE APP_SCHEMA DEVICE_ID ENTITY_ID NAME DEVICE_CLASS POLL_INTERVAL MQTT_HOST MQTT_PORT MQTT_USER MQTT_PASSWORD

if [ -n "${DPS_ACTIVE:-}" ]; then export DPS_ACTIVE; fi
if [ -n "${DPS_BATTERY:-}" ]; then export DPS_BATTERY; fi

echo "[tuya-bridge] Starting. Device: $DEVICE_ID → MQTT as $ENTITY_ID (class=$DEVICE_CLASS) every ${POLL_INTERVAL}s"
exec /opt/venv/bin/python /bridge.py
