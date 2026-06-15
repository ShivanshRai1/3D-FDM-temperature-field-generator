# How To Run Onrender Optimized Version4

This copy is tuned for Render Free. It intentionally uses coarser solver limits than the main `New_Version4 _User_accounts` folder.

The full local user-account workflow is documented in:

```text
../HOW_TO_RUN.md
```

If user-account saved runs are enabled in a Render deployment, remember that the default implementation is file-backed. Render Free filesystems are ephemeral, so saved users and manifests can disappear after redeploys, restarts, or spin-downs unless persistent storage is added.

## Run Locally

From this folder:

```bash
cd "/Users/amolverma/Cursor/3D Steady-State Temperature field generator/New_Version4 _User_accounts/Onrender_optimized"
python3 server.py
```

Open:

```text
http://127.0.0.1:1085/pcb_temperature_app.html
```

If the port is busy:

```bash
python3 server.py --port 1086
```

## Render Free Limits

The app enforces demo-safe limits:

- estimated grid cells: `75,000` max,
- `dx >= 1.0 mm`,
- `dy >= 1.0 mm`,
- `dz >= 0.1 mm`,
- radiation iterations: `12` max,
- solver workers: `1` concurrent job.

These limits reduce accuracy compared with the main local Version4 solver. Use the main `New_Version4 _User_accounts` folder for fine-grid verification runs.

## Render Start Command

Use:

```bash
python3 server.py
```

The server reads Render's `PORT` environment variable and binds to `0.0.0.0` by default.

## Component Array Import

Click `Import Components Via Array` to switch from manual entry to the multi-row array UI. Click it again to return to manual entry.

The extended JSON component array format is:

```javascript
[
  [x, y, length, width, height, Rth_value, Rth_type, Rth_ca, Power_loss, "Component_Name"]
]
```

Use these rules for the Render-optimized copy:

- For `Rth_ja`: put the `Rth_ja` number in `Rth_value`, set `Rth_type` to `"junction_to_ambient"`, and set `Rth_ca` to `null`.
- For `Rth_jc + Rth_ca`: put the `Rth_jc` number in `Rth_value`, set `Rth_type` to `"junction_to_case"`, and put the `Rth_ca` number in `Rth_ca`.
- `Power_loss` is the only power-dissipation column.

Example using `Rth_ja = 28 K/W`:

```javascript
[[10, 8, 5, 5, 1.2, 28, "junction_to_ambient", null, 3.5, "MOSFET_RthJA"]]
```

Example using `Rth_jc = 7 K/W` and `Rth_ca = 13 K/W`:

```javascript
[[20, 8, 5, 5, 1.2, 7, "junction_to_case", 13, 3.5, "MOSFET_RthJC"]]
```

Legacy rows `[x, y, length, width, height, Rth, Power_loss, "Component_Name"]` still import as `Rth_ja`.

Imported components use the power value in each row. After import, components can still be edited, dragged, resized, and removed normally.

## Manifests

Simulation manifests are still written to:

```text
temp/simulation_runs/<job_id>.json
```

On Render Free, the filesystem is ephemeral. Manifests can disappear after redeploys, restarts, or spin-downs. The same applies to `temp/user_accounts.json` if user-account features are deployed with this copy.

## Tests

```bash
python3 -m pytest -o cache_dir=/private/tmp/pcb_pytest_cache tests/test_solver.py
```

Expected:

```text
11 passed
```
