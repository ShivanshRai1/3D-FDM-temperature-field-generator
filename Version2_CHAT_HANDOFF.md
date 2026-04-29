# Version2 Project Handoff: 3D PCB Steady-State Temperature Field Generator

## Project Location

Workspace:

```text
/Users/amolverma/Cursor/3D Steady-State Temperature field generator
```

Active project folder:

```text
Version2/
```

Main files:

```text
Version2/pcb_temperature_app.html
Version2/server.py
Version2/temperature_field/solver.py
Version2/temperature_field/models.py
Version2/SOLVER_MATH.md
Version2/HOW_TO_RUN.md
Version2/README.md
Version2/tests/test_solver.py
```

Run app:

```bash
cd "/Users/amolverma/Cursor/3D Steady-State Temperature field generator/Version2"
python3 server.py
```

Open:

```text
http://127.0.0.1:8080/pcb_temperature_app.html
```

Run tests:

```bash
cd "/Users/amolverma/Cursor/3D Steady-State Temperature field generator/Version2"
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Original Goal

Build a browser-based frontend and Python backend to generate a 3D steady-state PCB temperature field from:

1. Component locations and PCB size.
2. Component power dissipation.
3. Steady-state thermal resistance from datasheet transient thermal impedance curves.
4. Copper layers and thermal vias.

Methodology should follow the paper:

```text
A 3D Finite Difference Method for Obtaining the Steady-state Temperature Field of a PCBCircuit.pdf
```

Component equivalent conductivity is computed from user-entered Rth:

```text
k = height / (R_th * length * width)
```

All dimensions are converted to meters internally, so `k` is in `W/mK`.

## Current Frontend State

Main frontend file:

```text
Version2/pcb_temperature_app.html
```

It is a Three.js browser application that lets the user:

- Move PCB components in x/y.
- Keep all components fixed to the top PCB surface; component z follows PCB thickness.
- Add/remove copper layers.
- Add/remove thermal vias.
- Auto-generate PCB size from component bounding box plus user margin.
- Toggle X-Ray mode to see vias/layers through the PCB.
- Run simulation via local Python backend.
- View results as 3D result, top view, bottom view, and per-layer 2D temperature fields.
- Hover temperature tiles to see exact temperature.
- Download CSV, PNG, HTML snapshot, and config JSON.

Important UI behavior already implemented:

- Left setup panel is collapsible.
- Three.js canvas centers correctly relative to the current workspace.
- Opening/closing the left panel should no longer force the camera into bottom view.
- On simulation completion, setup panel is hidden and a dedicated results mode appears.
- Results panel contains result state, 3D/top/bottom/layer buttons, run log, component summary, and Edit Setup button.
- Temperature range legend no longer overlaps the results panel; in results mode it is offset left of the panel.
- Result rendering hides PCB/layer/via base colors by default so the temperature gradient is primary.
- `Show Layers/Vias` overlays layers/vias on the result view if needed.

## Current Backend/API State

Backend server:

```text
Version2/server.py
```

Important API endpoints:

```text
POST /api/simulate/start
GET  /api/simulate/status?job_id=...
POST /api/simulate
```

The frontend uses the async job flow:

1. `POST /api/simulate/start`
2. Server starts solver in a background thread and immediately returns `job_id`.
3. Frontend polls `/api/simulate/status?job_id=...`.
4. Final result is returned when job status is `done`.

This was added because long-running HTTP requests were being closed by the browser, producing:

```text
ConnectionResetError
BrokenPipeError
HTTP 0
```

Server now catches broken pipe / connection reset while writing JSON.

## Current Solver State

Main solver:

```text
Version2/temperature_field/solver.py
```

Current method:

- Cartesian finite-volume / finite-difference heat balance.
- One unknown temperature per grid cell.
- Sparse matrix system `A T = b`.
- Conductance between neighboring cells uses harmonic mean of thermal conductivity.
- Boundary uses convection and linearized radiation.
- Component heat is distributed over top PCB cells under the component footprint.
- Copper layers are rasterized into z-cells.
- Vias are rasterized into cylindrical cell masks.
- Component conductivity is set using `k_component = height / (R_th * length * width)`.

Solve behavior:

```python
DIRECT_SOLVE_CELL_LIMIT = 50_000
```

- If cells <= 50,000: use direct sparse `spsolve`.
- If cells > 50,000: use preconditioned sparse Conjugate Gradient.
- This was changed because direct solve on grids like `84 x 66 x 32 = 177,408` cells could kill the Python process.

Known issue: the sparse matrix is still assembled using `lil_matrix` before converting to CSR. For large grids, this assembly is still memory-heavy. A future fix should assemble COO/CSR directly.

## Ambient Temperature Handling

Ambient handling was corrected after a double-counting bug.

Previous bug:

- Backend solved in Kelvin around backend ambient.
- Frontend then did:

```js
displayC = (solverK - 273.15) + ambientC
```

This double-counted ambient.

Correct current behavior:

- Frontend sends user ambient into backend boundary:

```js
config.boundary = {
  ambient_temperature_k: ambientC + 273.15,
  surrounding_temperature_k: ambientC + 273.15,
  convection_coefficient_w_m2k: 13.0,
  emissivity: 0.8
}
```

- Frontend display conversion is:

```js
displayC = solverK - 273.15
```

Run log text should say ambient is applied inside the solver boundary condition.

## Numerical Accuracy Concerns

The user observed results like:

```text
Temperature range: 277.6 °C - 631.1 °C
Buck regulator estimated junction: 391.22 °C
Power resistor estimated junction: 413.76 °C
MOSFET estimated junction: 701.10 °C
```

For configuration roughly:

```text
Buck regulator: 1.8 W, Rth 22 K/W
Power resistor: 0.75 W, Rth 55 K/W
MOSFET: 10 W, Rth 7 K/W
PCB: 42 x 33 x 1.6 mm
Grid: dx=0.5 mm, dy=0.5 mm, dz=0.05 mm
```

Concern: these temperatures look too high and are not trustworthy as physical predictions yet.

Important explanation:

- The temperature field max is the PCB/component-field temperature.
- Component summary previously showed `estimated junction = board/field max under component + P * Rth`.
- This made it look inconsistent with the visible field range.

UI summary was changed to separate:

```text
Field max under footprint
Rth junction rise
Estimated junction
Power
Rth
```

The underlying solver still has major modeling limits.

## Key Accuracy Limitations Still Present

Do not treat the current solver as validated for design decisions.

Major issues:

1. Copper layers are thin, e.g. `0.035 mm`, but uniform `dz` often does not resolve them exactly.
2. Current copper model assigns copper conductivity to any z-cell whose center lies in the layer. If no z-cell center lands inside, nearest z-cell becomes copper. This can overrepresent copper thickness.
3. Better approach is a nonuniform z grid with cell planes aligned to copper layer start/end.
4. Component heat is injected directly into top PCB cells, not through a separate package/contact/case model.
5. Rth is currently used to derive equivalent component conductivity and also used to estimate junction temperature. This double use is conceptually questionable.
6. Radiation is linearized once at initial ambient, so high-temperature radiation is under-modeled.
7. Boundary condition is simple natural convection plus radiation on exposed board faces.
8. Sparse matrix assembly is memory-heavy for fine grids.
9. CG convergence residual is matrix residual, not necessarily a full physical validation metric.
10. Current temperatures may be very sensitive to `dx/dy/dz` and heat-source rasterization.

## Important User Preferences / Requirements

User wants:

- Browser-based app.
- Three.js frontend.
- Components movable in x/y only; fixed to PCB top.
- PCB size generated from component min/max plus margin.
- Add/remove copper layers and vias interactively.
- Copper layer placement should lock to ZX stack view.
- Via placement should lock to XY view.
- X-Ray mode to see layers/vias through PCB.
- Simulation modal should show ambient temperature in °C, legacy SOR omega, dx/dy/dz, and explanation of why grid is needed.
- Progress bar with current solver status.
- On simulation completion: dedicated results page/mode, run log, component summary, view buttons, downloadable CSV/PNG/HTML.
- Temperature results shown in °C.
- Avoid color conflicts between base PCB/layer colors and temperature gradient.
- Accuracy matters more than just having a visually plausible result.

## Current Result Flow

Frontend call sequence:

```js
runSimulationFromModal()
  -> build solverConfig()
  -> add boundary ambient in K
  -> runSolverJob(config, omega, startedAt)
      -> POST /api/simulate/start
      -> poll GET /api/simulate/status?job_id=...
  -> applySolverResult(payload, runLog)
  -> openResultsPage()
```

Backend job sequence:

```python
_run_solver_job()
  -> _build_config()
  -> solve_steady_state()
  -> _payload_from_result()
  -> mark job status done
```

## Known Runtime Fixes Already Done

### HTTP 0 / BrokenPipe

Cause:

- Browser closed long-running request before backend wrote final response.

Fix:

- Switched to async job + polling.

### `NameError: temp is not defined`

Cause:

- During async refactor, part of `_payload_from_result()` was accidentally left after `_run_solver_job()`.

Fix:

- Moved layer view and final response construction back into `_payload_from_result()`.

### Direct sparse solve crash

Cause:

- `spsolve` on around 177k cells was too memory-heavy.

Fix:

- Lowered direct solve cutoff to 50k cells.
- Larger grids use preconditioned CG.

### Ambient double-count

Cause:

- Backend used ambient in Kelvin, frontend added ambient again after K-to-C conversion.

Fix:

- Send ambient to backend in K.
- Frontend displays `K - 273.15`.

## Suggested Next Engineering Step

The next chat should focus on solver correctness, not UI.

Recommended next task:

```text
Refactor solver to use a physically cleaner thermal model:
1. Nonuniform z-grid aligned to copper layers.
2. Separate PCB field, component case/contact, and junction temperature.
3. Stop using Rth both as component conductivity and junction-rise term unless explicitly intended.
4. Direct COO/CSR sparse assembly instead of LIL.
5. Add validation cases with analytic/lumped comparisons.
```

High-priority implementation plan:

1. Replace uniform z-axis with nonuniform z grid:
   - z planes include `0`, `pcb_thickness`, every copper layer start/end, and component heat/contact depth.
   - Use thin cells around copper, coarser cells in FR4.
   - Update face areas/distances per cell.
2. Clean component thermal model:
   - Treat `P * Rth` as junction-to-board/case rise only for summary.
   - Do not also use Rth-derived conductivity unless a separate component solid model is explicitly chosen.
   - For now, apply component power as heat flux over footprint on top PCB surface/contact cells.
3. Correct temperature reporting:
   - Field temperature = solved PCB/cell temperature.
   - Case/contact temperature = field/contact max or average under footprint.
   - Junction estimate = case/contact temperature + `P * Rth`.
   - UI must label these separately.
4. Improve matrix assembly:
   - Build COO row/col/data arrays directly.
   - Convert to CSR once.
   - Avoid `lil_matrix` for large systems.
5. Add validation tests:
   - zero-power board returns ambient,
   - single uniform board with known heat/convection gives reasonable lumped rise,
   - copper layer exists as exact z slab in nonuniform grid,
   - changing ambient shifts absolute temps correctly without double-count,
   - component summary junction rise equals `field_contact_temp + P*Rth`.

## Current Commands to Verify

```bash
cd "/Users/amolverma/Cursor/3D Steady-State Temperature field generator/Version2"

python3 -m unittest discover -s tests -p 'test_*.py'

node -e "const fs=require('fs'),vm=require('vm');const html=fs.readFileSync('pcb_temperature_app.html','utf8');const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);scripts.forEach((s,i)=>new vm.Script(s,{filename:'inline-'+i+'.js'}));console.log('inline scripts syntax ok:', scripts.length);"
```

Run app:

```bash
python3 server.py
```

Open:

```text
http://127.0.0.1:8080/pcb_temperature_app.html
```

## Last Known User Sentiment

User is not confident in accuracy of current numerical results, especially with high temperatures like `277-631 °C` field range and `701 °C` MOSFET estimated junction. This concern is valid.

The UI is mostly acceptable now. Solver physics and validation are the main remaining problems.
