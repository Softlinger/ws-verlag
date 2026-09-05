# Produktiv-Image der WS-Verlag Verwaltung (fuer Synology Container Manager).
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /srv/app

RUN pip install --no-cache-dir poetry==2.4.2

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# Nicht-root-Benutzer: der App-Container braucht (bewusst) keinerlei erhoehte Rechte
# und hat insbesondere keinen Zugriff auf den Docker-Socket - nur der Updater-Container hat das.
RUN useradd --create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Test-Build: gleiches Basis-Image, zusaetzlich die dev-Abhaengigkeiten (pytest) und
# die Test-Suite. Wird nur per `docker compose --profile test run --rm test` gebaut/
# ausgefuehrt (siehe docker-compose.yml), NICHT im normalen App-Image.
FROM base AS test
USER root
RUN poetry install --no-root
COPY tests ./tests
# test_release.py importiert deploy.release - nur die benoetigten Skripte kopieren,
# damit weder .env.deploy (FTP-Secrets) noch release_upload/ ins Image gelangen.
COPY deploy/release.py deploy/deploy_release.py ./deploy/
USER appuser
WORKDIR /srv/app
# no:cacheprovider - appuser darf das Read-only-Image nicht beschreiben (.pytest_cache).
CMD ["pytest", "-q", "-p", "no:cacheprovider"]
