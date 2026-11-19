# Barcode Contact Map Studio

A custom [Seqera Studio](https://docs.seqera.io/platform-cloud/studios/overview) that serves the Barcode Contact Map viewer over `.bcm` bundles in mounted cloud storage. The bundles are read in place from the mount; nothing is copied into the Studio.

The bundles come from [robsyme/stlfr-barcode-contacts](https://github.com/robsyme/stlfr-barcode-contacts), a Nextflow pipeline that turns stLFR linked reads into per-chromosome barcode co-occurrence maps.

## Add it to a workspace

1. In Studios, choose **Add Studio**, then **Import from Git**, and give this repository's URL.
2. Under **Mount data**, pick the folder that holds the pipeline's `bcm/` output (or the `bcm/` folder itself).
3. Start the Studio and connect.

The landing page lists every folder under `/workspace/data` that contains `.bcm` files as one sample, and links to the viewer with all of that sample's chromosomes loaded. If the mount also contains a `multiqc_report.html`, the page links to it.

## What is in here

Platform reads only `.seqera/`:

- `.seqera/studio-config.yaml`: tells Platform to build the Studio from the Dockerfile.
- `.seqera/Dockerfile`: `python:3.12-slim` plus Seqera's `connect-client`.
- `.seqera/app/server.py`: a standard-library HTTP server on `$CONNECT_TOOL_PORT`. `/` is the sample list, `/viewer/` the static viewer, `/data/` the read-only mount.
- `.seqera/app/viewer/`: the viewer (`index.html`) and its guide, single static pages with no external requests.

## Settings

Environment variables, all optional:

| Variable | Default | Meaning |
|---|---|---|
| `BCM_DATA_ROOT` | `/workspace/data` | Folder to scan for bundles |
| `BCM_SCAN_DEPTH` | `6` | How many folder levels to scan |
| `BCM_SCAN_MAX_DIRS` | `5000` | Stop scanning after this many folders |
| `BCM_SCAN_TTL` | `30` | Seconds to cache the scan |

A running Studio sees new files in the mount only if `FUSION_REFRESH_TIMEOUT` was set when it was created, so start it after the pipeline has finished.

## Run it locally

```bash
docker build -t bcm-studio .seqera
docker run --rm --entrypoint python3 -e CONNECT_TOOL_PORT=8080 -p 8080:8080 \
  -v /path/to/results:/workspace/data/results:ro bcm-studio /app/server.py
```

Then open http://localhost:8080.
