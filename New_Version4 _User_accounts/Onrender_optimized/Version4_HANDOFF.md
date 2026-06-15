# Version4 Handoff: 3D PCB Steady-State Temperature Field Generator

## Project Context

The active working implementation is currently in:

```text
Version3/
```

`Version2/` was intentionally preserved as a working baseline. `Version3/` was created as a full copy of `Version2/` before solver changes were made.

The next development target is `Version4/`. This folder currently contains this handoff only.

## Current Version3 State

Main files:

```text
Version3/pcb_temperature_app.html
Version3/server.py
Version3/temperature_field/solver.py
Version3/temperature_field/models.py
Version3/temperature_field/io.py
Version3/tests/test_solver.py
Version3/README.md
Version3/HOW_TO_RUN.md
Version3/SOLVER_MATH.md
```

Run the Version3 browser app:

```bash
cd "/Users/amolverma/Cursor/3D Steady-State Temperature field generator/New_Version4 _User_accounts"
python3 server.py
```

Open:

```text
http://127.0.0.1:1085/pcb_temperature_app.html
```

If port `1085` is already in use, New_Version4 _User_accounts now prints a clear message. You can either open the already-running server or run another port:

```bash
python3 server.py --port 1086
```

New_Version4 _User_accounts also supports:

```bash
PORT=1086 python3 server.py
```

Run tests:

```bash
cd "/Users/amolverma/Cursor/3D Steady-State Temperature field generator/New_Version4 _User_accounts"
python3 -m unittest discover -s tests -p 'test_*.py'
```

Expected current result:

```text
Ran 8 tests
OK
```

## Version3 Solver Changes Already Implemented

Version3 is a more efficient single-machine sparse finite-volume solver. It is not a full HPC solver yet.

Implemented changes:

- Nonuniform `z` grid aligned to copper layer start/end planes.
- Thin copper layers, for example `0.035 mm`, are represented as exact z slabs instead of being inflated to the nearest coarse `dz` cell.
- `dx` and `dy` remain uniform.
- User `dz_mm` is now interpreted as a maximum target z-cell thickness, not forced uniform z spacing.
- Component heat is distributed by x/y footprint overlap into surface heat cells, so components smaller than one x/y cell still inject full power.
- Component `Rth` is no longer applied as board-cell conductivity in the default solve.
- Component thermal resistance now requires an explicit mode:

```text
thermal_resistance_mode = "junction_to_ambient":
T_junction = T_ambient + power_w * Rth_ja

thermal_resistance_mode = "junction_to_case":
T_junction = T_ambient + power_w * (Rth_jc + Rth_ca)
```

- The `junction_to_case` mode requires `case_to_ambient_thermal_resistance_k_per_w`.
- `T_junction = T_board + power_w * Rth` should only be used for a thermal-resistance path explicitly referenced to the sampled board/contact temperature. It is not valid for `Rth_ja`, and bare `Rth_jc` still needs a case path.
- The board solve reaches steady state by solving the zero-heat-accumulation balance directly: component heat input equals conduction redistribution plus convection/radiation losses at exposed faces.

- The equivalent component conductivity value is still reported for traceability:

```text
k = height / (Rth * length * width)
```

- Sparse matrix assembly was changed from `lil_matrix` to direct COO arrays followed by CSR conversion.
- Small systems still use direct sparse solve.
- Larger systems use Jacobi-preconditioned Conjugate Gradient.
- Solver diagnostics are returned in the API payload.

Key diagnostics:

```text
cell_count
grid_shape
matrix_nonzeros
total_power_w
boundary_loss_w
energy_balance_error_w
exact_radiation_boundary_loss_w
exact_radiation_balance_error_w
radiation_outer_iterations_used
min_dx_mm / max_dx_mm
min_dy_mm / max_dy_mm
min_dz_mm / max_dz_mm
```

## Version3 Server And Frontend State

Server:

```text
Version3/server.py
```

Important API endpoints:

```text
POST /api/simulate/start
GET  /api/simulate/status?job_id=...
POST /api/simulate
```

The browser app uses the async job flow:

1. `POST /api/simulate/start`
2. backend creates a background solver thread and returns `job_id`
3. frontend polls `/api/simulate/status?job_id=...`
4. final result is returned when status is `done`

New_Version4 _User_accounts server defaults to:

```text
127.0.0.1:1085
```

Frontend fallback backend URL in `pcb_temperature_app.html` is:

```text
http://127.0.0.1:1085/api/simulate
```

Frontend result panel now shows:

- requested `dx/dy/dz`
- actual z cell range
- matrix shape and unknown count
- matrix nonzero count
- solver iterations
- radiation outer iterations
- residual
- model energy balance error

## Validation Already Run

Version3 validation commands previously passed:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

```bash
node -e "const fs=require('fs'),vm=require('vm');const html=fs.readFileSync('pcb_temperature_app.html','utf8');const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);scripts.forEach((s,i)=>new vm.Script(s,{filename:'inline-'+i+'.js'}));console.log('inline scripts syntax ok:', scripts.length);"
```

```bash
PYTHONPYCACHEPREFIX=/tmp/version3_pycache python3 -m compileall temperature_field server.py
```

```bash
python3 -m temperature_field.cli examples/sample_pcb.json --out outputs/sample_result.npz --summary outputs/sample_summary.json
```

Representative fine-grid probe from Version3:

```text
board: 42 x 33 x 1.6 mm
requested grid: dx=0.5 mm, dy=0.5 mm, dz=0.05 mm
layers: FR4, 0.035 mm bottom copper, 0.035 mm top copper
component: 10 W MOSFET, 6 x 6 mm footprint, Rth=7 K/W
grid shape: 84 x 66 x 34
cells: 188,496
solve time: about 0.55 s
max field temperature: about 374.5 degC
model energy balance error: about 4e-6 W
```

When `radiation_outer_iterations=8` was tested manually on the same representative case:

```text
solve time: about 3.3 s
outer iterations used: 8
max field temperature: about 330.2 degC
exact radiation balance error: about 4.7e-4 W
```

This shows that high-temperature cases benefit from nonlinear radiation outer iterations, but the frontend currently sends:

```javascript
config.radiation_outer_iterations = 1;
config.radiation_tolerance_k = 0.05;
```

## Accuracy Limitations Still Present

Do not treat Version3 as validated for design-signoff thermal prediction yet.

Known limitations:

- Boundary conditions are still simple natural convection plus radiation on exposed rectangular board faces.
- Radiation is linearized once by default in the frontend.
- Component package/contact physics are still simplified.
- Junction reporting uses either `P * Rth_ja` from ambient or `P * (Rth_jc + Rth_ca)` from ambient, depending on the selected component mode.
- Vias are still laterally rasterized by x/y cell center, not by exact via-area fraction.
- Components are not modeled as separate 3D package solids with explicit thermal contact resistance.
- No board mounting, airflow, enclosure, heatsink, or copper trace pattern detail.
- No analytic benchmark suite beyond smoke/regression tests.
- No measured-data calibration.

## HPC Assessment

Version3 uses some HPC-aligned numerical choices:

- sparse matrix formulation
- COO-to-CSR assembly
- vectorized NumPy assembly of neighbor conductances
- iterative CG for larger systems
- nonuniform z grid to reduce unnecessary cells
- matrix and solve diagnostics

Version3 is not yet an HPC-grade solver:

- no multiprocessing
- no MPI or distributed memory
- no GPU acceleration
- no multigrid preconditioner
- no matrix-free operator
- no adaptive mesh refinement
- no formal performance benchmark suite

## Recommended Version4 Work

High-impact next steps:

1. Add a Version4 folder by copying Version3 before editing:

```bash
cp -R Version3 Version4
```

Because this handoff already exists in `Version4/`, copy carefully if preserving it:

```bash
cp -R Version3/* Version4/
```

2. Add frontend controls for nonlinear radiation:

- `radiation_outer_iterations`
- `radiation_tolerance_k`
- display exact radiation balance error separately from model energy balance error

Recommended default:

```text
radiation_outer_iterations = 4
radiation_tolerance_k = 0.1 K
```

Use `1` for fast exploratory runs and `4-8` for high-temperature final checks.

3. Improve via modeling:

- replace center-based via rasterization with x/y area-fraction overlap
- conserve via cross-sectional area more accurately on coarse grids
- add tests comparing via area on coarse and fine grids

4. Add an HPC-style benchmark script:

```text
benchmarks/benchmark_solver.py
```

Track:

- grid shape
- cell count
- matrix nonzeros
- assembly time
- solve time
- iterations
- peak memory if practical
- energy balance error
- max temperature

Benchmark cases:

- no heat
- single component on FR4
- single component with top/bottom copper
- thermal via array
- fine-grid representative PCB

5. Evaluate better preconditioning:

- first candidate: PyAMG algebraic multigrid preconditioner
- keep SciPy-only path as fallback
- compare CG iterations and wall time versus current Jacobi preconditioner

6. Consider matrix-free CG after benchmark data exists:

- avoid storing the full sparse matrix
- implement matvec from conductance arrays
- keep CSR path until matrix-free is tested against it

7. Add validation cases:

- lumped board thermal resistance estimate
- 1D slab conduction with known analytic solution
- ambient shift invariance
- power conservation
- copper slab exact-thickness test
- via-area conservation
- nonlinear radiation convergence trend

## Suggested Version4 Acceptance Criteria

Version4 should be considered successful if:

- existing Version3 tests still pass
- new via area-fraction tests pass
- nonlinear radiation controls are visible and wired through the API
- benchmark script produces repeatable timing and accuracy output
- representative fine-grid case runs without memory spikes
- PyAMG, if added, is optional and has a clean fallback when unavailable
- Version2 and Version3 remain runnable
