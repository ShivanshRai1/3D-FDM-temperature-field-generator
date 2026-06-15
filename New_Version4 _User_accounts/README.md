# Version4 User Accounts: 3D Steady-State PCB Temperature Field Generator

This is the local Version4 implementation of the paper's steady-state 3D finite-difference methodology for PCB temperature fields. It includes the browser-based PCB modeller, Python sparse thermal solver backend, and a local user-account layer for saving and reopening selected simulation results.

Version4 solves the board as a 3D finite-volume grid with:

- harmonic-mean conduction between neighboring cells,
- nonuniform z cells aligned to copper-layer start/end planes,
- component power distributed by footprint overlap into the top PCB surface cells,
- convection on every exposed boundary face,
- linearized gray-body radiation on every exposed boundary face,
- sparse linear solve of the finite-difference steady-state equations.

The implementation uses a finite-volume form of the same heat balance from the paper. This keeps units explicit: neighbor terms are conductances in W/K, component sources are W, and boundary losses are W/K to ambient.

## User Account Experience

The top-right user account menu contains the active user selector plus:

- `Re-run Guide`,
- `Saved Runs`,
- `New Setup`,
- `New User`.

Each solver run writes a manifest to:

```text
temp/simulation_runs/<job_id>.json
```

New manifests default to `saved: false`. The result appears immediately for inspection, but it only appears in `Saved Runs` after the user clicks `Save Run` on the results page. Saving updates the same manifest to `saved: true` and records the active user:

```json
"account": {"user_id": "...", "display_name": "..."},
"user": {"user_id": "..."},
"saved": true
```

Saved simulations are restored from the manifest setup snapshot and stored response payload. This recreates the setup, 3D result view, component summary, run log, and solver completion panel without rerunning the solver.

## Files

- `pcb_temperature_app.html`: browser-based Three.js PCB configurator and temperature-field viewer.
- `server.py`: local HTTP server, `/api/simulate` backend, account endpoints, and saved-run endpoints.
- `temperature_field/models.py`: input dataclasses.
- `temperature_field/solver.py`: 3D finite-difference/finite-volume solver.
- `temperature_field/io.py`: JSON config loading and result writing.
- `temperature_field/thermal_resistance.py`: helper for extracting steady-state Rth from transient Zth curves.
- `temperature_field/cli.py`: command line runner.
- `examples/sample_pcb.json`: complete example input.
- `tests/test_solver.py`: solver smoke and regression tests.
- `SOLVER_MATH.md`: mathematical description of the finite-difference sparse solve.

## Run

Run the browser app with the Python solver backend:

```bash
cd "New_Version4 _User_accounts"
python3 server.py
```

Then open `http://127.0.0.1:8000/pcb_temperature_app.html`.

The HTML app lets users place components, copper layers, and thermal vias, auto-generates PCB size from component extents plus margin, exports the solver handoff JSON, calls the backend solver from `Run Simulation`, and saves selected completed runs under local user IDs.

If the page appears stale after a code update, restart `server.py` and open:

```text
http://127.0.0.1:8000/pcb_temperature_app.html?v=user-accounts
```

From the `New_Version4 _User_accounts` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m temperature_field.cli examples/sample_pcb.json --out outputs/sample_result.npz --summary outputs/sample_summary.json
```

For a quick run without a venv, use:

```bash
cd "New_Version4 _User_accounts"
python3 -m temperature_field.cli examples/sample_pcb.json --out outputs/sample_result.npz --summary outputs/sample_summary.json
```

## Input Model

The solver JSON input contains:

- `board`: PCB size and requested grid spacing in millimeters.
- `components`: PCB footprint, dissipated power, thermal-resistance mode, and thermal-resistance values in K/W.
- `copper_layers`: copper layer z extents and thermal conductivity in the frontend/API payload.
- `thermal_vias`: optional conductive via cylinders or arrays.
- `boundary`: ambient, surrounding temperature, convection coefficient, and emissivity.
- `solver`: initial temperature, relaxation factor, tolerance, and iteration limit.

Component locations use the lower-left footprint corner `(x_mm, y_mm)`. Power is applied into the top PCB cells under the footprint by default. In Version4, `dz_mm` is treated as the maximum target z-cell thickness; copper layer boundaries are inserted as exact z planes, so a 0.035 mm copper layer is represented as a 0.035 mm slab instead of being expanded to the nearest coarse cell.

Component thermal resistance must be identified as one of the supported paths:

```text
Rth_ja: Tj = ambient_temperature + power_w * Rth_ja
Rth_jc + Rth_ca: Tj = ambient_temperature + power_w * (Rth_jc + Rth_ca)
Rth_jb: Tj = solved_board_temperature + power_w * Rth_jb
Rth_jc + measured Tcase: Tj = measured_case_temperature + power_w * Rth_jc
Rth_jc + Rth_cb: Tj = solved_board_temperature + power_w * (Rth_jc + Rth_cb)
Rth_jb + Rth_ba: Tj = ambient_temperature + power_w * (Rth_jb + Rth_ba)
```

Use `thermal_resistance_mode` to choose the path. Secondary values use `secondary_thermal_resistance_k_per_w`, except measured case temperature, which uses `reference_temperature_k`.

The UI pre-fills these editable power-package defaults when a thermal-resistance mode is selected: `Rth_ja = 25 K/W`, `Rth_jc = 0.8 K/W`, `Rth_jb = 3 K/W`, `Rth_cb = 2 K/W`, `Rth_ca = 15 K/W`, `Rth_ba = 25 K/W`, and measured `Tcase = 35 °C`. `Rth_ca = 15 K/W` assumes a heatsink or airflow path.

The older shortcut `Tj = T_board + power_w * Rth` is only defensible when `Rth` is explicitly a junction-to-board or junction-to-case-to-board path referenced to the same board temperature being sampled. It is not valid for datasheet `Rth_ja`, because `Rth_ja` already includes the ambient path, and it is not valid for bare `Rth_jc` unless a case-to-ambient or case-to-board path is also modeled.

The board field reaches steady state because the finite-volume equations solve the time-independent heat balance: component heat sources equal conduction redistribution plus convection and radiation losses at exposed surfaces. If the boundary losses are positive and the linearized radiation/convection terms are well posed, the sparse system has a stable equilibrium temperature field for the simplified model.

The solver reports user-entered steady-state thermal resistance as an equivalent component thermal conductivity for traceability:

```text
k = height / (R_th * length * width)
```

Use SI units in the calculation. In the JSON, dimensions are entered in millimeters and converted internally to meters before computing `k`, so the result is W/mK. Version4 no longer applies this equivalent conductivity to PCB cells during the default board solve; Rth is used for the junction-rise estimate only.

If a datasheet gives a transient thermal impedance curve instead of a direct steady-state value, either read the long-time plateau manually or provide a component `transient_thermal_impedance_curve` in JSON. Inline form:

```json
"transient_thermal_impedance_curve": [
  {"time_s": 1.0, "zth_k_per_w": 4.2},
  {"time_s": 10.0, "zth_k_per_w": 9.1},
  {"time_s": 100.0, "zth_k_per_w": 12.0},
  {"time_s": 1000.0, "zth_k_per_w": 12.2}
]
```

CSV form is also supported with `time_s,zth_k_per_w` columns:

```json
"transient_thermal_impedance_curve": "curves/component_zth.csv"
```

The loader estimates Rth from the tail of the curve and rejects curves that have not reached a stable plateau.

## Result Files

The `.npz` output contains:

- `x_m`, `y_m`, `z_m`: grid center coordinates.
- `x_edges_m`, `y_edges_m`, `z_edges_m`: grid cell edge coordinates.
- `temperature_k`: 3D temperature field in kelvin.
- `conductivity_w_mk`: material conductivity field.
- `heat_w`: power assigned to each cell.
- `summary_json`: convergence and component temperature summary.

The summary JSON is easier to inspect directly and includes min/max/mean board temperature, per-component board/junction estimates, sparse matrix diagnostics, total power, boundary loss, and energy balance error.

## Tests

```bash
cd "New_Version4 _User_accounts"
python3 -m pytest -o cache_dir=/private/tmp/pcb_pytest_cache tests/test_solver.py
```

Expected result:

```text
11 passed
```
