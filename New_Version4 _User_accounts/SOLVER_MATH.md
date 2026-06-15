# Solver Mathematics

This document describes what the Version3 backend solves mathematically.

## Governing Equation

The steady-state heat equation is:

```text
div(k grad(T)) + q = 0
```

Where:

- `T` is temperature in kelvin.
- `k` is thermal conductivity in `W/(m K)`.
- `q` is heat generation represented as watts assigned to finite-volume cells.

The implementation uses a finite-volume form on a Cartesian x/y grid with a nonuniform z grid. Each cell stores one unknown temperature.

## Grid

The frontend still sends requested spacing:

```text
dx, dy, dz
```

The backend computes uniform x/y cells:

```text
nx = ceil(board_length / dx)
ny = ceil(board_width / dy)
actual_dx = board_length / nx
actual_dy = board_width / ny
```

The z axis is nonuniform. Cell planes always include:

```text
z = 0
z = board_thickness
every copper layer z_start and z_end
component heat/contact depth planes
```

The remaining FR4 gaps are split so no z cell is thicker than requested `dz`. This means `dz` is a maximum target spacing, not a forced uniform spacing. Thin copper layers such as 0.035 mm are represented by exact 0.035 mm z slabs.

The number of unknowns in the sparse solve is:

```text
N = nx * ny * nz
```

Each unknown is one cell temperature.

## Material Field

Every cell is assigned a conductivity. The first layer is the default board material, usually FR4:

```text
k = 0.35 W/(m K)
```

Copper layers are defined by `z_start_mm` and `z_end_mm`. A cell receives copper conductivity when its z interval overlaps that layer:

```text
z_cell_end > z_start and z_cell_start < z_end
```

Because layer start/end planes are inserted into the z grid, the solver no longer expands thin copper layers to the nearest full coarse cell.

Thermal vias are still rasterized laterally by cell center:

```text
(x_cell - x_via)^2 + (y_cell - y_via)^2 <= radius_via^2
z_cell overlaps via z range
```

Components are top-mounted. Their heat footprint is applied to the top cells under the component footprint using exact x/y overlap area, so components smaller than one cell still inject their full power into the overlapped cell.

The equivalent conductivity implied by user-entered steady-state thermal resistance is still reported:

```text
k_component = height / (R_th * length * width)
```

All dimensions are converted to meters before this formula is applied, so `k_component` is in `W/(m K)`. Version3 does not apply this equivalent conductivity to PCB cells in the default solve; Rth is used for junction-rise reporting only.

## Cell-to-Cell Conductance

Each cell exchanges heat with its six neighbors:

```text
+x, -x, +y, -y, +z, -z
```

The face conductivity between adjacent cells uses the harmonic mean:

```text
k_face = 2 * k_cell * k_neighbor / (k_cell + k_neighbor)
```

The conductance between two cells is:

```text
G_face = k_face * A_face / d_face
```

For x-direction faces:

```text
A_face = dy[j] * dz[k]
d_face = 0.5 * (dx[i] + dx[i+1])
```

For y-direction faces:

```text
A_face = dx[i] * dz[k]
d_face = 0.5 * (dy[j] + dy[j+1])
```

For z-direction faces:

```text
A_face = dx[i] * dy[j]
d_face = 0.5 * (dz[k] + dz[k+1])
```

## Boundary Conditions

For missing neighbors at the outside board boundary, the solver applies convection and linearized radiation.

Convection conductance:

```text
G_conv = h * A_face
```

Linearized radiation coefficient:

```text
h_rad = epsilon * sigma * (T_ref + T_sur) * (T_ref^2 + T_sur^2)
```

Radiation conductance:

```text
G_rad = h_rad * A_face
```

By default, `T_ref = initial_temperature`, which keeps the system linear. The solver also supports bounded outer iterations that update `T_ref` from the latest solved temperature for high-temperature cases.

The boundary contribution for one exposed face is:

```text
(G_conv + G_rad) * T_cell = G_conv * T_air + G_rad * T_sur
```

## Sparse Matrix System

For each cell `p`, the heat balance is:

```text
sum(G_pn * (T_p - T_n)) + sum(G_boundary * T_p) = Q_p + sum(G_boundary * T_boundary)
```

This is assembled into:

```text
A T = b
```

For each neighbor `n`:

```text
A[p, p] += G_pn
A[p, n] -= G_pn
```

For each exposed boundary face:

```text
A[p, p] += G_conv + G_rad
b[p] += G_conv * T_air + G_rad * T_sur
```

For component heat:

```text
b[p] += Q_p
```

Component power is distributed in proportion to footprint overlap with heat-source cells:

```text
Q_p = component_power * overlap_weight_p / sum(overlap_weight)
```

## Solve

The backend assembles COO row/column/value arrays directly, converts once to CSR sparse format, and solves:

```text
T = scipy sparse solve(A, b)
```

Small systems use a direct sparse solve. Larger systems use Jacobi-preconditioned Conjugate Gradient.

The returned convergence indicator is based on the sparse residual:

```text
residual = A T - b
max_delta = max(abs(residual))
converged = max_delta < tolerance
```

For a direct sparse solve, `iterations = 1`. The legacy SOR omega value in the frontend is not used by the sparse solver. It remains visible only as a reference/future fallback parameter.

## Diagnostics

The result summary reports:

- grid shape and total cell count,
- sparse matrix nonzeros,
- total applied component power,
- model boundary loss from the same linearized radiation model used in the solve,
- model energy balance error,
- exact Stefan-Boltzmann boundary-loss check for high-temperature awareness,
- radiation outer iterations used.

## Important Modeling Limits

Version3 fixes the earlier nearest-z-cell copper approximation by aligning z planes to copper layer boundaries. Lateral via and component footprints are still limited by the x/y grid, although component heat uses area overlap instead of center inclusion.

The current component model applies heat into top board cells under the component footprint and estimates junction temperature afterward using the user-selected thermal-resistance path:

```text
Rth_ja mode:
T_junction = T_ambient + power * Rth_ja

Rth_jc + Rth_ca mode:
T_junction = T_ambient + power * (Rth_jc + Rth_ca)

Rth_jb mode:
T_junction = T_board + power * Rth_jb

Rth_jc + measured Tcase mode:
T_junction = T_case_measured + power * Rth_jc

Rth_jc + Rth_cb mode:
T_junction = T_board + power * (Rth_jc + Rth_cb)

Rth_jb + Rth_ba mode:
T_junction = T_ambient + power * (Rth_jb + Rth_ba)
```

Modes with paired thermal resistances require the secondary resistance. The measured-case mode requires measured case temperature.

The shortcut `T_junction = T_board + power * R_th` is not a general package model. It is only appropriate when the chosen `R_th` is referenced to that same board/contact temperature, for example a calibrated junction-to-board path. For `Rth_ja`, the reference is ambient. For `Rth_jc`, a case path is still required.

The steady-state field is reached by solving the algebraic heat-balance equations directly, not by simulating transient time marching. At equilibrium, every cell has zero net heat accumulation:

```text
sum(conductive heat leaving cell) + boundary heat loss = heat generated in cell
```

Convection and radiation boundary terms provide the heat sink to ambient/surroundings. Radiation is nonlinear in temperature, so the implementation linearizes it and optionally repeats outer iterations until the radiation reference temperature is consistent with the solved temperature field.

Radiation is linearized using the initial temperature by default. Outer radiation iterations improve accuracy for high-temperature cases at extra solve cost.

The sparse solve now avoids LIL assembly and is faster for fine grids, but grid quality, boundary-condition assumptions, and component/package modeling still control physical accuracy.
