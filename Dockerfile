ARG BUILD_FROM=ghcr.io/home-assistant/$BUILD_ARCH-base:latest
FROM $BUILD_FROM

# OS deps
RUN apk add --no-cache bash python3 py3-pip jq

# PEP 668: use a venv
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Python deps
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir 'paho-mqtt<2' requests tinytuya

# Add files
COPY run.sh /run.sh
COPY bridge.py /bridge.py
RUN chmod +x /run.sh

CMD [ "/run.sh" ]
