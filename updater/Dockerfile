# Privilegierter Updater-Sidecar. Nur dieser Container erhaelt Docker-Socket-Zugriff -
# niemals der App-Container. Nicht nach aussen exponieren (kein Port-Publish).
FROM python:3.11-slim

WORKDIR /srv/updater

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY updater.py ./

CMD ["python", "updater.py"]
