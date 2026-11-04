# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
RUN --mount=type=secret,id=proxy_ca \
    apt-get -o Acquire::https::CaInfo=/etc/ssl/certs/ca-certificates.crt update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /bin/bash vscode
# Public, pinned DMR CLI; it packages the GGUF into the sidecar, not a paid service.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    python3 -c 'import urllib.request,hashlib,tarfile,io; b=urllib.request.urlopen("https://github.com/docker/model-runner/releases/download/dmr-v0.1.0/dmr-linux-amd64.tar.gz").read(); assert hashlib.sha256(b).hexdigest()=="9100ab1da129198b76eacb9c3cef66f254bfef644318dee5efda9b227aac3dd1"; t=tarfile.open(fileobj=io.BytesIO(b)); f=t.extractfile("dmr"); open("/usr/local/bin/dmr","wb").write(f.read())' \
    && chmod 755 /usr/local/bin/dmr
USER vscode
WORKDIR /workspaces/foxrun
