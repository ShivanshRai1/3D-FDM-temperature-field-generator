# How To Run Version4 User Accounts

This folder contains the local Version4 browser frontend, Python sparse thermal solver backend, and user-account/saved-run experience.

## 1. Run The Browser App With Solver Backend

From the project root:

```bash
cd "/Users/amolverma/Cursor/3D Steady-State Temperature field generator/New_Version4 _User_accounts"
python3 server.py
```

The terminal should print:

```text
Serving Version4 User Accounts from /Users/amolverma/Cursor/3D Steady-State Temperature field generator/New_Version4 _User_accounts
Open http://127.0.0.1:1085/pcb_temperature_app.html
Press Ctrl+C to stop.
```

Open:

```text
http://127.0.0.1:1085/pcb_temperature_app.html
```

If the browser still shows an old UI, open with a cache-busting query:

```text
http://127.0.0.1:1085/pcb_temperature_app.html?v=user-accounts
```

If port `1085` is already in use:

```bash
python3 server.py --port 1086
```

Then open:

```text
http://127.0.0.1:1086/pcb_temperature_app.html
```

Stop the server by pressing `Ctrl+C` in the terminal running `server.py`.

## 2. User Accounts And Saved Runs

The top-right user button opens the account menu. It contains:

- user selector,
- `Re-run Guide`,
- `Saved Runs`,
- `New Setup`,
- `New User`.

Default users are:

```text
User Alpha
User Beta
User Gamma
```

`New User` creates another local user entry. Account metadata is stored in:

```text
temp/user_accounts.json
```

Each completed simulation creates a manifest, but it is not listed in `Saved Runs` until the user clicks `Save Run` on the results page. New run manifests default to:

```json
"saved": false
```

After `Save Run`, the backend updates the manifest to:

```json
"saved": true
```

The manifest also stores:

```json
"account": {"user_id": "...", "display_name": "..."},
"user": {"user_id": "..."}
```

`Saved Runs` only shows completed manifests where `saved` is `true` and the saved user matches the active account.

## 3. Simulation Run Manifests

Every backend simulation writes a JSON manifest here:

```text
temp/simulation_runs/<job_id>.json
```

The manifest stores:

- raw frontend request,
- active user metadata,
- `saved` state,
- setup snapshot for exact UI restoration,
- normalized solver config,
- board, component, copper-layer, thermal-via, boundary, and solver settings,
- timing fields,
- full solver response payload,
- component reports,
- top, bottom, and copper-layer temperature view arrays.

Saved runs are reopened by loading the manifest, restoring the setup snapshot, and rendering the stored result payload. The progress/completion panel is also restored from the manifest timing and solver residual.

## 4. Frontend Workflow

In the browser app:

1. Select or create a user from the top-right account menu.
2. Configure the Board section.
3. Add components manually or import a component array.
4. Add or remove copper layers.
5. Add or remove thermal vias.
6. Click `Run Simulation`.
7. In the Run Solver dialog:
   - set ambient temperature,
   - confirm `dx`, `dy`, and `dz`,
   - set radiation iterations,
   - run the solver.
8. Inspect the Results panel.
9. Click `Save Run` only if the result is worth keeping.
10. Use `Saved Runs` to reopen saved simulations later.
11. Click `Edit Setup` to leave result mode and return to the normal simulation modeller.

Toolbar controls:

- `Top`: top view.
- `Bottom`: bottom view.
- `Iso`: isometric view.
- Layer dropdown: choose the active copper layer.
- `X-Ray`: show internal copper/vias.
- `Run Simulation`: start the backend solver.
- `CSV`: export the active temperature slice.
- `PNG`: save the current canvas view.
- `HTML`: export the configured page.

Account menu controls:

- `Re-run Guide`: starts the setup guide on the setup page, or the results guide on the results page.
- `Saved Runs`: lists saved manifests for the active user.
- `New Setup`: returns to a fresh setup.
- `New User`: creates a local user account entry.

## 5. Component Array Import

Click `Import Components Via Array` to switch from manual entry to the multi-row array UI. Click it again to return to manual entry. Each row has one power-loss field; the thermal-resistance fields only describe the junction-temperature estimate.

The extended JSON component array format is:

```javascript
[
  [x, y, length, width, height, Primary_Rth, Rth_mode, Secondary_Rth, Measured_Tcase_C, Power_loss, "Component_Name"]
]
```

Use these rules:

- `junction_to_ambient`: primary is `Rth_ja`; secondary and measured case are `null`.
- `junction_to_case_to_ambient`: primary is `Rth_jc`; secondary is `Rth_ca`; measured case is `null`.
- `junction_to_board`: primary is `Rth_jb`; secondary and measured case are `null`.
- `junction_to_measured_case`: primary is `Rth_jc`; secondary is `null`; measured case is the measured case temperature in Celsius.
- `junction_to_case_to_board`: primary is `Rth_jc`; secondary is `Rth_cb`; measured case is `null`.
- `junction_to_board_to_ambient`: primary is `Rth_jb`; secondary is `Rth_ba`; measured case is `null`.
- `Power_loss` is the only power-dissipation column.

The UI pre-fills these default values when a thermal-resistance mode is selected:

```text
Rth_ja = 25 K/W
Rth_jc = 0.8 K/W
Rth_jb = 3 K/W
Rth_cb = 2 K/W
Rth_ca = 15 K/W
Rth_ba = 25 K/W
Tcase = 35 °C
```

Legacy rows `[x, y, length, width, height, Rth, Power_loss, "Component_Name"]` still import as `Rth_ja`.

If `Rth` or a required secondary value is missing, the component is flagged and simulation is blocked until the user completes the selected thermal-resistance path.

## 6. API Endpoints

The browser `Run Simulation` flow calls:

```text
POST /api/simulate/start
GET  /api/simulate/status?job_id=...
```

User-account and saved-run endpoints:

```text
GET  /api/accounts
POST /api/accounts
GET  /api/simulations?user_id=...
GET  /api/simulations/detail?job_id=...&user_id=...
POST /api/simulations/save
```

`POST /api/simulations/save` updates an existing completed manifest. It does not rerun the solver.

If `/api/simulations/save` returns `Unknown endpoint`, an old server process is running. Stop it and restart `New_Version4 _User_accounts/server.py`.

## 7. Run The Solver Example

From `New_Version4 _User_accounts`:

```bash
python3 -m temperature_field.cli examples/sample_pcb.json --out outputs/sample_result.npz --summary outputs/sample_summary.json
```

Expected output looks like:

```text
Converged: True after ... iterations
Grid shape: [...]
Maximum board temperature: ... K
```

## 8. Run Tests

From `New_Version4 _User_accounts`:

```bash
python3 -m pytest -o cache_dir=/private/tmp/pcb_pytest_cache tests/test_solver.py
```

Expected result:

```text
11 passed
```

## Solver Notes

The backend converts frontend geometry into the Python solver model, runs the 3D sparse finite-volume heat-balance solver, and returns top, bottom, and copper-layer temperature slices.

The exposed PCB boundaries use convection plus radiation. They are not fixed-temperature perfect heatsinks.

See `SOLVER_MATH.md` for the matrix assembly and boundary-condition equations.
