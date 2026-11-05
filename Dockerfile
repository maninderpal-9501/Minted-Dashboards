# Minted pages server (FastAPI + uvicorn, MCP client of the Ekyam Dev MCP server)
#   docker build -t minted-server .                                  # small image, Excel without recalculation
#   docker build -t minted-server --build-arg WITH_LIBREOFFICE=1 .   # + LibreOffice to recalculate Excel formulas
FROM python:3.12-slim

ARG WITH_LIBREOFFICE=0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

RUN if [ "$WITH_LIBREOFFICE" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends libreoffice-calc fonts-dejavu-core \
      && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY pages ./pages

# run as a non-root user; HOME is needed by LibreOffice for its profile
RUN useradd --create-home --uid 10001 minted && chown -R minted /srv
USER minted
ENV HOME=/home/minted

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

# One worker on purpose: the warm-up scheduler runs inside the process (more workers = duplicate runs).
# The app is async, so one worker handles many page requests at once.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --workers 1"]
