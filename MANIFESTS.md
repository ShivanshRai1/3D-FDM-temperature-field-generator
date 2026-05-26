# Simulation Run Manifests

Every browser or API simulation creates a JSON manifest with the full setup, normalized solver config, timing, and result summary. This supports run traceability and later comparison of setups and outcomes.

## Storage location

By default, manifests are written to:

```text
temp/simulation_runs/<job_id>.json
```

On a deployed server, that resolves to a folder next to `server.py`, for example:

```text
/home/reactfe/3D-FDM-temperature-field-generator/temp/simulation_runs/
```

Override the folder with:

```bash
export MANIFEST_DIR=/path/to/manifest/folder
```

The directory is created automatically if it does not exist.

## Manifest schema

Each file uses schema:

```text
pcb_thermal_simulation_run_manifest_v1
```

Typical fields:

- `job_id`, `mode`, `status`, `created_at`, `updated_at`, `finished_at`
- `raw_request` — exact request sent by the frontend
- `source_config` — frontend geometry and settings
- `normalized_config` — solver-ready board, components, layers, vias, boundary, solver settings
- `result_summary` — convergence, temperatures, component reports, view metadata
- `timing` — solver start/finish timestamps and wall time
- `error` — failure message when a run does not complete

## HTTP access

No SSH is required to browse saved runs if the server is running.

List recent manifests:

```text
GET /api/manifests
GET /api/manifests?limit=50
```

Download one manifest:

```text
GET /api/manifests/<job_id>
```

Examples on DigitalOcean:

```text
http://165.22.212.92:8000/api/manifests
http://165.22.212.92:8000/api/manifests/<job_id>
```

After a successful browser run, the Results panel also links directly to that run's manifest.

## Optional GitHub sync

Render deployments can mirror manifests into GitHub with:

- `MANIFEST_SYNC_MODE=github`
- `MANIFEST_GITHUB_REPO`
- `MANIFEST_GITHUB_BRANCH`
- `MANIFEST_GITHUB_PATH`
- `MANIFEST_GITHUB_TOKEN`

This is optional. A server folder is enough for Part 1 storage requirements.

## Verify on the server

After running one simulation:

```bash
ls -lt ~/3D-FDM-temperature-field-generator/temp/simulation_runs/ | head
curl http://127.0.0.1:8000/api/manifests
```

You should see a new `<job_id>.json` file and the same run in the API index.
