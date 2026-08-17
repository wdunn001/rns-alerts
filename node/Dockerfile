# nomadnet-alerts: NomadNet node serving the active-alert pages alertd renders
# into the shared volume (static, MeshData-tagged micron that Beacon crawls).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir nomadnet
ENTRYPOINT ["nomadnet"]
CMD ["--config", "/config/nomadnet", "--rnsconfig", "/config/rns", "--daemon", "--console"]
