# Research Brief: 3D Steady-State PCB Temperature Field Generator

## Purpose Of This Document

This document is designed as source material for NotebookLM to generate a technical presentation. It summarizes the current program, solver implementation, optimization strategy, and frontend/results experience for anyone trying to understand, reproduce, or extend this project.

The project is a browser-based 3D PCB thermal simulation tool backed by a Python sparse finite-volume solver. Users can create a PCB setup, add components, copper layers, and thermal vias, run a steady-state thermal simulation, then inspect board and component temperatures through a 3D interface.

The current local build in `New_Version4 _User_accounts/` also includes a lightweight user-account workflow. Users can switch local user IDs, inspect completed results, explicitly save worthwhile runs, and later reopen those saved runs without rerunning the solver.

## 1. Current Implementation

### Project Goal

The program estimates steady-state temperature fields in a printed circuit board using a 3D heat-balance model. The goal is not to replace calibrated CFD or full package-level thermal simulation, but to provide a fast, interactive engineering tool for early-stage PCB thermal exploration.

The workflow is:

1. Select or create a local user account.
2. Define the board size and boundary conditions.
3. Add heat-generating components.
4. Add copper layers and thermal vias.
5. Choose solver resolution and radiation iterations.
6. Run a sparse steady-state thermal solve.
7. Inspect top, bottom, and copper-layer temperature fields.
8. Save the run only if it is worth keeping.
9. Reopen saved runs later from the active user account.
10. Export results and run manifests for verification.

### Research Paper Basis

The implementation is based on the project’s referenced research paper on steady-state 3D finite-difference PCB temperature-field generation. The paper motivates solving the board as a discretized 3D thermal conduction problem, with component heat sources and heat rejection at exposed surfaces.

Citation placeholder:

```text
[Insert exact paper title/authors here]
Steady-state 3D finite-difference methodology for PCB temperature fields.
```

How the paper maps into this implementation:

- The paper’s steady-state heat equation is implemented as a finite-volume heat balance.
- PCB material regions are represented as cells with thermal conductivity.
- Component heat dissipation is inserted as source power.
- Heat spreads by conduction between neighboring cells.
- Exposed board surfaces reject heat by convection and radiation.
- The discretized system is solved as a sparse linear system.

### Current Version Structure

Main implementation files:

```text
New_Version4 _User_accounts/
  pcb_temperature_app.html
  server.py
  temperature_field/
    solver.py
    models.py
    io.py
    thermal_resistance.py
    plotting.py
    cli.py
  tests/test_solver.py
  SOLVER_MATH.md
  HOW_TO_RUN.md
```

Deployment-optimized copy:

```text
New_Version4 _User_accounts/Onrender_optimized/
```

The Render-optimized version is intentionally limited for Render Free compute constraints. It uses coarser grid limits, fewer radiation iterations, and one active solver worker.

### Current Capabilities

The current program supports:

- interactive 3D PCB setup,
- component placement and removal,
- component array import,
- copper-layer placement and removal,
- thermal-via placement and removal,
- board convection coefficient input,
- ambient temperature input,
- configurable grid spacing,
- nonlinear radiation outer iterations,
- sparse backend solve,
- top, bottom, and layer temperature views,
- CSV, PNG, HTML, and JSON exports,
- simulation run manifests for verification,
- guide/onboarding overlay for new users,
- local user selector and user creation,
- saved-run catalog filtered by active user,
- saved-run restoration from JSON manifests,
- context-aware `Re-run Guide` from setup or results pages.

### User Accounts And Saved Runs

The user-account layer is intentionally local and file-backed. It is not an authenticated cloud account system. The goal is to let multiple local users or test identities keep separate saved-run lists during development.

Account metadata is stored in:

```text
temp/user_accounts.json
```

Every completed solver job writes a manifest to:

```text
temp/simulation_runs/<job_id>.json
```

New manifests default to:

```json
"saved": false
```

The results page includes `Save Run`. Clicking it updates the manifest to:

```json
"saved": true,
"account": {"user_id": "...", "display_name": "..."},
"user": {"user_id": "..."}
```

`Saved Runs` lists only manifests where:

```text
manifest.status == "done"
manifest.saved == true
manifest.user/account matches the active user_id
```

Opening a saved run does not rerun the solver. The frontend restores:

- setup snapshot,
- stored response payload,
- result views,
- component summary,
- run log,
- completion/progress panel text.

This design makes the temporary JSON manifests the source of truth for saved simulation history.

### Component Array Import

The frontend supports importing components with:

```javascript
[[x, y, length, width, height, Primary_Rth, Rth_mode, Secondary_Rth, Measured_Tcase_C, Power_loss, "Component_Name"]]
```

Example:

```javascript
[[10, 8, 5, 5, 1.2, 25, "junction_to_ambient", null, null, 3.5, "MOSFET"]]
```

After import, components remain fully editable. The user can drag them, resize them, edit power, switch among the supported thermal-resistance paths, and remove them.

## 2. Solver Implementation

### Governing Equation

The solver is based on the steady-state heat equation:

```text
div(k grad(T)) + q = 0
```

Where:

- `T` is temperature in kelvin.
- `k` is thermal conductivity in `W/(m K)`.
- `q` is heat generation represented as watts assigned to finite-volume cells.

The implementation uses a finite-volume form on a Cartesian x/y grid and a nonuniform z grid. Each grid cell contains one unknown temperature.

### Grid Model

The frontend sends requested spacing:

```text
dx, dy, dz
```

The solver computes:

```text
nx = ceil(board_length / dx)
ny = ceil(board_width / dy)
```

The x and y grids are uniform.

The z grid is nonuniform. It inserts exact planes at:

- bottom board surface,
- top board surface,
- copper layer start and end planes,
- component heat/contact depth planes.

This is important because PCB copper can be very thin, for example `0.035 mm`. A uniform coarse z grid would either miss that copper layer or incorrectly inflate it. The current solver represents thin copper layers as exact z slabs.

### Material Assignment

The base board is usually FR4:

```text
k_FR4 = 0.35 W/(m K)
```

Copper layers use:

```text
k_Cu = 385 W/(m K)
```

Thermal vias are rasterized into the grid by checking whether cell centers fall inside the via radius and whether the cell overlaps the via z range.

### Component Heat Sources

Components are treated as surface heat sources. Their power is distributed into top board cells under the component footprint.

The distribution uses x/y footprint overlap, not just cell-center inclusion. This allows components smaller than a grid cell to still inject their full power into the model.

For each component:

```text
Q_cell = component_power * overlap_weight_cell / sum(overlap_weight)
```

### Conductance Between Cells

Each cell exchanges heat with up to six neighbors:

```text
+x, -x, +y, -y, +z, -z
```

The solver computes conductance:

```text
G = k_face * area / distance
```

The face conductivity between two neighboring cells uses the harmonic mean:

```text
k_face = 2 * k_cell * k_neighbor / (k_cell + k_neighbor)
```

This is standard for finite-volume conduction across material interfaces.

### Boundary Conditions

The PCB boundaries are not perfect heatsinks. They are not fixed to ambient temperature.

Each exposed board face rejects heat through:

```text
convection + radiation
```

Convection:

```text
G_conv = h * A
```

Linearized radiation:

```text
h_rad = epsilon * sigma * (T_ref + T_sur) * (T_ref^2 + T_sur^2)
G_rad = h_rad * A
```

The boundary heat balance contribution is:

```text
(G_conv + G_rad) * T_cell = G_conv * T_air + G_rad * T_sur
```

The user can set convective coefficient `h` in the Board section.

Example h values:

- natural convection: `5-15 W/m²K`,
- weak forced airflow: `30-60 W/m²K`,
- directed airflow: `60-120 W/m²K`,
- strong forced/ducted flow: `120-250+ W/m²K`.

### Radiation Outer Iterations

Radiation is nonlinear because radiative heat loss depends on `T^4`.

The solver linearizes radiation with a reference temperature `T_ref`. For high-temperature cases, one pass can produce unrealistic results. The current frontend therefore supports radiation outer iterations:

1. Solve using current radiation reference temperature.
2. Use the solved temperature as the next radiation reference.
3. Repeat until tolerance or iteration limit.

The result payload reports:

- model energy balance error,
- exact radiation boundary loss,
- exact radiation balance error,
- radiation outer iterations used.

This is important because a linearized model can appear balanced while exact radiation is not.

### Sparse Matrix System

The finite-volume equations are assembled into:

```text
A T = b
```

Where:

- `A` is the sparse conductance matrix,
- `T` is the unknown temperature vector,
- `b` is heat source and boundary contribution vector.

For each internal face:

```text
A[p, p] += G
A[p, n] -= G
```

For each exposed boundary face:

```text
A[p, p] += G_boundary
b[p] += G_boundary * T_boundary
```

For each heat source:

```text
b[p] += Q_cell
```

### Solver Backend

The backend uses SciPy sparse solvers:

- direct sparse solve for small systems,
- Jacobi-preconditioned Conjugate Gradient for larger systems.

The sparse residual is:

```text
residual = A T - b
max_delta = max(abs(residual))
```

The solver reports:

- convergence flag,
- residual,
- iteration count,
- cell count,
- matrix nonzero count,
- total power,
- boundary loss,
- energy balance error,
- exact radiation balance error.

### Junction Temperature Reporting

The current implementation requires users to identify the available thermal-resistance path before adding or importing components. `RθJA` is self-contained:

```text
T_junction = T_ambient + power * RθJA
```

If the datasheet value is `RθJC`, the UI requires the missing case-to-ambient path:

```text
T_junction = T_ambient + power * (RθJC + RθCA)
```

This avoids mixing incompatible datasheet thermal resistance meanings. The board field still reports the maximum temperature under each component footprint separately from the junction estimate.

The shortcut `T_junction = T_board + power * Rth` is only appropriate when `Rth` is explicitly referenced to the sampled board/contact temperature, for example a calibrated junction-to-board value. It is not valid for `RθJA`, and it is incomplete for bare `RθJC`.

The PCB temperature field reaches steady state because the solver assumes zero transient heat storage and solves the finite-volume heat-balance equations directly. At equilibrium, component heat input equals conduction redistribution plus convection and radiation loss through exposed board faces. Radiation is nonlinear, so high-temperature runs require outer radiation iterations to make the linearized boundary condition consistent with the final temperature field.

## 3. Optimization And HPC Principles

### Existing Optimizations

The solver already uses several HPC-aligned numerical choices:

1. Sparse matrix formulation.
2. Direct COO row/column/value assembly.
3. Single conversion from COO to CSR.
4. Vectorized NumPy operations for face conductances.
5. Jacobi-preconditioned Conjugate Gradient for larger systems.
6. Nonuniform z grid to avoid wasting cells while preserving thin layers.
7. Radiation outer iteration limit to control nonlinear solve cost.

### Why Sparse Matrices Matter

A dense matrix for a 3D grid would be impossible for realistic cases.

Example:

```text
N = 170,850 cells
dense matrix entries = N^2 ≈ 29 billion entries
```

But the sparse matrix only stores local neighbor connections:

```text
~7 nonzeros per cell
```

Recent example:

```text
cells: 170,850
matrix nonzeros: about 1,176,244
```

This is tractable on a local machine and allows interactive use for medium grids.

### Amdahl’s Law View

Speedup from HPC depends on the parallelizable fraction:

```text
Speedup(N) = 1 / ((1 - P) + P / N)
```

Line-count estimates suggested about `43-50%` of solver code is obviously parallelizable. Runtime profiling suggests a higher practical fraction because sparse assembly and sparse solve dominate runtime.

If only half the code is parallelizable:

```text
maximum speedup ≈ 2x
```

If 90% of runtime is parallelizable:

```text
maximum speedup ≈ 10x
```

The best HPC targets are:

- sparse matrix assembly,
- iterative sparse solve,
- preconditioning,
- radiation outer-loop solve sequence,
- component/via rasterization for large layouts,
- boundary loss reductions.

### Parallelizable Regions

The following operations are naturally parallel:

- compute x-face, y-face, and z-face conductances,
- compute boundary contributions for six faces,
- compute heat source weights for many components,
- compute via conductivity masks,
- matrix-vector products inside iterative solvers,
- reductions for boundary loss and energy balance.

The following are mostly serial or low-value to parallelize:

- input validation,
- dataclass construction,
- grid edge generation,
- small component report formatting,
- JSON serialization,
- UI state management.

### Future HPC Directions

Future solver upgrades could include:

1. PETSc or Trilinos backend for scalable sparse linear solves.
2. Algebraic multigrid preconditioning.
3. GPU sparse solve with CuPy or similar libraries.
4. Matrix-free stencil operator to avoid explicitly storing `A`.
5. Domain decomposition for very large boards.
6. Parallel component/via rasterization.
7. Benchmark suite for cell count, memory, and solve time.
8. Server-side job queue and worker pool.

### Render Free Optimized Version

The project includes:

```text
New_Version4 _User_accounts/Onrender_optimized/
```

This copy is tuned for Render Free hosting. It uses conservative limits:

- estimated grid cells: `75,000` max,
- `dx >= 1.0 mm`,
- `dy >= 1.0 mm`,
- `dz >= 0.1 mm`,
- radiation iterations: `12` max,
- solver workers: `1`.

This is intended for demos and quick screening, not fine-grid verification.

## 4. Frontend And Results UI/UX

### Frontend Technology

The frontend is a single browser HTML application using:

- Three.js for 3D visualization,
- plain JavaScript for state and controls,
- Python HTTP backend for simulation.

The UI is designed around an interactive PCB workspace rather than a static form.

### Setup Panel

The left setup panel includes:

- Board settings,
- component inputs,
- component array import,
- copper-layer controls,
- thermal-via controls,
- selected-object editing,
- solver handoff/export tools.

Board controls include:

- auto margin,
- PCB thickness,
- convective coefficient.

Component controls include:

- name,
- x/y position,
- length/width/height,
- power,
- Rth,
- add/remove,
- import array.

### Top Toolbar

The top toolbar includes:

- `Top`: top view,
- `Bottom`: bottom view,
- `Iso`: isometric view,
- `Layer`: layer slice view,
- layer dropdown,
- `X-Ray`: show internal layers/vias,
- `Run Simulation`,
- `CSV`,
- `PNG`,
- `HTML`.

The account menu is separate from the toolbar in the top-right corner. It contains the active user selector, `Re-run Guide`, `Saved Runs`, `New Setup`, and `New User`.

### Interactive Guide

The guide walks new users through:

1. Board setup.
2. Component addition/removal/import.
3. Copper layer addition/removal.
4. Thermal via addition/removal.
5. Solver setup.
6. Top toolbar controls.
7. Results interpretation.
8. Save Run behavior.

The guide is skippable. It highlights one UI region at a time and lets users click Next without performing the action. `Re-run Guide` starts the setup guide from setup pages and the results guide from the results page.

### Solver Dialog

The Run Solver dialog shows:

- estimated PCB dimensions,
- grid spacing,
- estimated matrix size,
- runtime warning,
- radiation iteration control,
- ambient temperature,
- residual tolerance.

The user can type custom `dx`, `dy`, and `dz`. The UI validates values only when Run Solver is clicked, so typing is not interrupted.

### Results Panel

The results panel displays:

- temperature range,
- selected result view buttons,
- top/bottom/layer fields,
- ambient temperature,
- grid spacing,
- actual z cell range,
- matrix size,
- matrix nonzeros,
- solver iterations,
- radiation outer iterations,
- residual,
- linearized energy balance error,
- exact radiation balance error,
- per-component board and junction estimates.
- `Save Run` for storing worthwhile completed simulations.

Long text wraps vertically. The panel avoids horizontal scrolling.

### Temperature Visualization

The app renders:

- 3D board geometry,
- component boxes,
- copper layer visualization,
- thermal vias,
- temperature-colored top/bottom/layer slices,
- component top temperature tiles,
- hover tooltips with exact sampled temperature.

### Run Manifests

Every backend simulation writes a JSON manifest:

```text
temp/simulation_runs/<job_id>.json
```

The manifest stores all important input and output data:

- raw frontend request,
- user/account metadata,
- saved state,
- setup snapshot,
- normalized solver model,
- board/component/layer/via data,
- boundary settings,
- solver settings,
- full result payload,
- full top/bottom/layer temperature arrays,
- timing information,
- diagnostics.

This enables reproducibility, verification, comparison between runs, saved-run restoration, and debugging.

## 5. Validation And Example Findings

Recent verified runs showed expected sensitivity to the convective coefficient `h`.

For the same board, grid, and power:

| Convection `h` | Max board temp | MOSFET junction estimate | Solver time |
|---:|---:|---:|---:|
| `13 W/m²K` | about `564 °C` | about `669 °C` | about `6.1 s` |
| `50 W/m²K` | about `427 °C` | about `532 °C` | about `1.8 s` |
| `100 W/m²K` | about `355 °C` | about `460 °C` | about `1.3 s` |

Trend:

- increasing convection lowers temperature,
- stronger convection reduces nonlinear radiation difficulty,
- exact radiation balance error stays near zero when enough outer iterations are used.

Interpretation:

- Numerically, the solver results are internally consistent.
- Physically, these high temperatures indicate missing cooling paths or unacceptable design conditions.
- The simplified model should not be treated as design-signoff thermal prediction without calibration.

## 6. Known Limitations

The current model has important limitations:

1. Components are not modeled as full 3D package solids.
2. Component-to-board contact resistance is simplified.
3. Heat is injected into board top cells rather than through a detailed package stack.
4. Boundary conditions are simplified convection and radiation on rectangular board faces.
5. Airflow is represented only by a scalar convection coefficient.
6. Radiation uses linearization and outer iterations, not a full nonlinear solve.
7. The UI now clarifies `RθJA` versus `RθJC + RθCA`, but package/contact physics are still simplified.
8. Thermal vias are rasterized by grid cells and may need finer grids for small diameters.
9. Render Free deployment is intentionally coarse and lower accuracy.

## 7. Recommended Future Work

Important next steps:

1. Extend the explicit Rth selector to additional package models if needed, such as junction-to-board or measured case-temperature workflows.
2. Update junction-temperature calculation based on Rth type.
3. Add package/case thermal model.
4. Add heatsink or fixed-temperature boundary options.
5. Add airflow presets for convection coefficient.
6. Add model calibration workflow using measured board temperatures.
7. Add memory and runtime estimator before simulation.
8. Add benchmark suite for grid size and solver performance.
9. Add persistent cloud storage for manifests.
10. Add HPC backend option for large runs.

## 8. Presentation Outline Suggested By This Document

Suggested slide structure:

1. Problem statement: fast interactive PCB thermal estimation.
2. Research-paper basis: steady-state 3D finite-difference/finite-volume heat balance.
3. System architecture: browser frontend, Python backend, sparse solver.
4. Input model: board, components, copper, vias, boundaries.
5. Solver math: heat equation, conductance, sparse matrix.
6. Boundary conditions: convection and radiation, not perfect heatsinks.
7. Radiation convergence: why outer iterations matter.
8. Optimization: sparse matrix, COO/CSR, CG, nonuniform z grid.
9. HPC analysis: Amdahl’s law and future parallelization.
10. UI workflow: setup panel, toolbar, guide, solver dialog.
11. Results UI: temperature fields, diagnostics, manifests.
12. Validation examples: convection sensitivity.
13. Limitations and accuracy caveats.
14. Future roadmap.
