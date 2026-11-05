# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
RUN --mount=type=secret,id=proxy_ca \
    apt-get -o Acquire::https::CaInfo=/etc/ssl/certs/ca-certificates.crt update \
    && apt-get install -y --no-install-recommends git curl ca-certificates procps ripgrep sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /workspaces/foxrun-state \
    && useradd --create-home --home-dir /workspaces/foxrun-state/user --uid 1000 --shell /bin/bash vscode
# Pin the real OpenCode host; verify its official release asset before installing.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    python3 -c 'import urllib.request,hashlib,tarfile,io; b=urllib.request.urlopen("https://github.com/anomalyco/opencode/releases/download/v1.19.5/opencode-linux-x64.tar.gz").read(); assert hashlib.sha256(b).hexdigest()=="588310a336fa3b9df36b3f0225b26f679d453efaad0cf3d66c3651ef3ec1647a"; t=tarfile.open(fileobj=io.BytesIO(b)); f=t.extractfile("opencode"); open("/usr/local/bin/opencode","wb").write(f.read())' \
    && chmod 755 /usr/local/bin/opencode \
    && mkdir -p /workspaces/foxrun-state \
    && chown vscode:vscode /workspaces/foxrun-state
USER vscode
WORKDIR /workspaces/foxrun
