# rns-alerts

NWS watches/warnings + emergency alerts (AMBER, civil, evacuation, shelter-in-place,
HazMat, fire) pushed over Reticulum via **LXMF**, with a browsable NomadNet node.

Subscribe from any LXMF client (Sideband/MeshChat/NomadNet) by messaging the alerts
node's LXMF address:

```
subscribe Boulder CO        # or a ZIP: subscribe 80301
severe|moderate|minor <place>   # set minimum severity (default: severe)
list                        # your subscriptions
unsubscribe                 # stop
help
```

AMBER + civil/evacuation/shelter alerts always come through regardless of the
severity setting. US only (NWS coverage). Data is fetched at the gateway from
api.weather.gov and pushed to subscribers, so the mesh delivers it off-grid.

## Pieces
- `alertd` - LXMF endpoint (command handler) + poll loop that fetches
  `api.weather.gov/alerts/active` per subscribed point, pushes matching alerts to
  subscribers (dedup ledger so a restart never re-blasts), and writes MeshData-tagged
  pages so Beacon indexes active alerts.
- `nomadnet-alerts` - node serving the active-alert pages (⚠ RNS-ALERTS).

Both connect to the .229 local rnsd hub (127.0.0.1:4343). Subscriptions + ledger in
a self-contained SQLite DB. Geocoding via the local Nominatim (.88:8092).
