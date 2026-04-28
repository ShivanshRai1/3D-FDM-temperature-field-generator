# How To Run Version3

This project has a browser frontend and a Python solver package.

## 1. Run The Browser App With Solver Backend

From the project root:

```bash
cd "/Users/amolverma/Cursor/3D Steady-State Temperature field generator/Version3"
python3 server.py
```

Then open:

```text
http://127.0.0.1:9023/pcb_temperature_app.html
```

This serves the Three.js configurator and enables the `Run Simulation` button to call the Python finite-difference solver.

The frontend currently loads Three.js and OrbitControls from CDN, so keep internet access enabled when opening the HTML file.

Stop the server with `Ctrl+C` in the terminal.

## 2. Frontend-Only Mode

You can still open `pcb_temperature_app.html` directly, but `Run Simulation` will not work because the Python API is not running.

From `Version3`:

```bash
open pcb_temperature_app.html
```

## 3. What To Test In The Frontend

In the browser app:

1. Drag components on the PCB.
2. Change the auto margin and confirm the PCB resizes.
3. Add and remove copper layers.
4. Test layer placement mode:
   - Click `Place Layer`.
   - The camera locks to the ZX stack view.
   - Hover/click through the PCB thickness to preview the layer z-position and the component portions intersected by the selected layer thickness.
   - Click `Apply Layer` to add it or `Cancel` to discard it.
5. Test via placement mode:
   - Click `Place Via`.
   - The camera locks to the XY top view.
   - Hover/click on the PCB to preview the via region.
   - Click `Apply Via` to add it or `Cancel` to discard it.
6. Click `Run Simulation` in the top toolbar.
   - Review the selected `dx`, `dy`, and `dz` values in the in-page dialog.
   - These grid values determine how many unknown temperatures are solved.
   - Smaller values resolve copper layers and component heat spreading better, but increase solve time.
7. Use `T`, `B`, `I`, and `Layer` view controls.
8. Hover over colored temperature tiles to see exact temperature values.
9. Download CSV, PNG, HTML snapshot, and Config JSON.

The `Config JSON` export is the handoff data intended for the backend solver. It includes:

- component box dimensions,
- component placement,
- PCB size,
- copper layer placement and extents,
- thermal via placement,
- component power,
- user-entered steady-state thermal resistance,
- equivalent thermal conductivity computed as:

```text
k = height / (R_th * length * width)
```

The calculation uses meters internally, so the result is `W/mK`.

## 4. Run The Solver Example

From `Version3`:

```bash
python3 -m temperature_field.cli examples/sample_pcb.json --out outputs/sample_result.npz --summary outputs/sample_summary.json
```

Expected output looks like:

```text
Converged: True after 1 iterations
Grid shape: [...]
Maximum board temperature: ... K
```

The result files are written to:

- `outputs/sample_result.npz`
- `outputs/sample_summary.json`

## 5. Run Tests

From `Version3`:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Expected result:

```text
Ran 8 tests
OK
```

## Solver Integration Note

The browser `Run Simulation` button calls the local Python backend at:

```text
POST /api/simulate/start
GET /api/simulate/status?job_id=...
```

The backend converts the frontend geometry into the Python solver model, runs the 3D finite-volume/finite-difference heat-balance solver, and returns top, bottom, and copper-layer temperature slices.

The frontend rendering integration point is:

```javascript
window.applySolverResult(payload)
```

The Python solver uses a 3D finite-volume/finite-difference heat-balance formulation assembled into a sparse linear system `A T = b`. Version3 uses nonuniform z cells aligned to copper layers and direct COO/CSR sparse assembly. The legacy SOR omega field remains in the dialog only for comparison or future fallback iterative runs; the sparse solver does not use omega.

See `SOLVER_MATH.md` for the exact matrix assembly and boundary-condition equations.
