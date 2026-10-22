FROM python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2

# Refresh OS trust and pip's independent bundled trust store.
COPY requirements-security.txt /tmp/requirements-security.txt
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip install --no-cache-dir --disable-pip-version-check \
    --only-binary=:all: --no-deps --require-hashes --upgrade \
    -r /tmp/requirements-security.txt \
 && rm /tmp/requirements-security.txt

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py commentary.json supplemental.json ./

CMD ["python", "-u", "app.py"]
