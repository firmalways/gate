# FirmAlways Gate container image.
#   docker run --rm -p 8787:8787 -e FIRMALWAYS_GATE_API_KEY=... -e OPENAI_API_KEY=... \
#     -v "$PWD/policy.toml:/etc/firmalways/policy.toml:ro" ghcr.io/firmalways/gate
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/firmalways/gate" \
      org.opencontainers.image.description="Open-source AI privacy gateway for Thai personal data (PDPA)" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[pdf]" && rm -rf /build \
 && useradd --create-home --uid 10001 gate \
 && mkdir -p /etc/firmalways /var/lib/firmalways && chown gate /var/lib/firmalways

USER gate
WORKDIR /var/lib/firmalways
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=2)"
ENTRYPOINT ["firmalways-gate"]
# Listens on all interfaces inside the container; set FIRMALWAYS_GATE_API_KEY or [[clients]] keys.
CMD ["serve", "--host", "0.0.0.0", "--port", "8787", "--policy", "/etc/firmalways/policy.toml"]
