# Render-Optimized Version4: 3D Steady-State PCB Temperature Field Generator

This folder is the Render Free oriented deployment copy. It is tuned for lower resource usage than the main local `New_Version4 _User_accounts` app.

The main local folder now includes a user-account and saved-run workflow:

- top-right user menu,
- `Saved Runs`,
- `Save Run`,
- `New Setup`,
- `New User`,
- `Re-run Guide`,
- file-backed manifests with `saved: true/false`.

Those saved-run records are stored under `temp/` in the local implementation. On Render Free, the filesystem is ephemeral, so user accounts and saved manifests should not be treated as durable unless a persistent backing store is added.

This copy solves the board as a 3D finite-volume grid with:

- harmonic-mean conduction between neighboring cells,
- nonuniform z cells aligned to copper-layer start/end planes,
- component power distributed by footprint overlap into the top PCB surface cells,
- convection on every exposed boundary face,
- linearized gray-body radiation on every exposed boundary face,
- sparse linear solve of the finite-difference steady-state equations.

The implementation uses a finite-volume form of the same heat balance from the paper. This keeps units explicit: neighbor terms are conductances in W/K, component sources are W, and boundary losses are W/K to ambient.

## Files

- `pcb_temperature_app.html`: browser-based Three.js PCB configurator and temperature-field viewer.
- `server.py`: local HTTP server and `/api/simulate` backend for the Python solver.
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

Then open `http://127.0.0.1:1085/pcb_temperature_app.html`.

The HTML app lets users place components, copper layers, and thermal vias, auto-generates PCB size from component extents plus margin, exports the solver handoff JSON, and calls the backend solver from `Run Simulation`.

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

The JSON input contains:

- `board`: PCB size and requested grid spacing in millimeters.
- `layers`: full-board material layers with z extents and thermal conductivity.
- `components`: PCB footprint, dissipated power, and steady-state thermal resistance in K/W.
- `thermal_vias`: optional conductive via cylinders or arrays.
- `boundary`: ambient, surrounding temperature, convection coefficient, and emissivity.
- `solver`: initial temperature, relaxation factor, tolerance, and iteration limit.

Component locations use the lower-left footprint corner `(x_mm, y_mm)`. Power is applied into the top PCB cells under the footprint by default. In Version4, `dz_mm` is treated as the maximum target z-cell thickness; copper layer boundaries are inserted as exact z planes, so a 0.035 mm copper layer is represented as a 0.035 mm slab instead of being expanded to the nearest coarse cell.

Component thermal resistance must be identified as one of two supported paths:

```text
Rth_ja: Tj = ambient_temperature + power_w * Rth_ja
Rth_jc + Rth_ca: Tj = ambient_temperature + power_w * (Rth_jc + Rth_ca)
```

Use `thermal_resistance_mode: "junction_to_ambient"` for datasheet `Rth_ja`. Use `thermal_resistance_mode: "junction_to_case"` only when `case_to_ambient_thermal_resistance_k_per_w` is also supplied.

The solver reports user-entered steady-state thermal resistance as an equivalent component thermal conductivity for traceability:

```text
k = height / (R_th * length * width)
```

Use SI units in the calculation. In the JSON, dimensions are entered in millimeters and converted internally to meters before computing `k`, so the result is W/mK. Version4 no longer applies this equivalent conductivity to PCB cells during the default board solve; Rth is used for the junction-rise estimate only.

The shortcut `Tj = T_board + power_w * Rth` is only defensible when `Rth` is explicitly referenced to the sampled board/contact temperature. It is not valid for datasheet `Rth_ja`, and bare `Rth_jc` still needs a case-to-ambient or case-to-board path.

The board field reaches steady state because the finite-volume equations solve the time-independent heat balance: component heat sources equal conduction redistribution plus convection and radiation losses at exposed surfaces.

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
