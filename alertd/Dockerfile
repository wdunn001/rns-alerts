# rns-alerts: LXMF-driven NWS/emergency alert push + poller.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir rns lxmf
COPY rns_alerts /app/rns_alerts
EXPOSE 8222
CMD ["python", "-m", "rns_alerts"]
