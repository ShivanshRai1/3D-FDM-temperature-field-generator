from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os

import numpy as np
from scipy import sparse
from scipy.sparse import linalg as sparse_linalg

from .models import Board, Component, Layer, SimulationConfig, ThermalVia

SIGMA_W_M2K4 = 5.670374419e-8
DIRECT_SOLVE_CELL_LIMIT = int(os.environ.get("SOLVER_DIRECT_SOLVE_CELL_LIMIT", "50000"))
EPS_M = 1e-12


@dataclass(frozen=True)
class Grid:
    x_edges_m: np.ndarray
    y_edges_m: np.ndarray
    z_edges_m: np.ndarray
    x_m: np.ndarray
    y_m: np.ndarray
    z_m: np.ndarray
    dx_m: np.ndarray
    dy_m: np.ndarray
    dz_m: np.ndarray


@dataclass
class ComponentReport:
    name: str
    board_average_temperature_k: float
    board_max_temperature_k: float
    estimated_junction_temperature_k: float
    equivalent_thermal_conductivity_w_mk: float
    occupied_cell_count: int
    junction_rise_k: float = 0.0
    component_model: str = "surface_heat_flux_plus_junction_rise"


@dataclass
class SimulationResult:
    config: SimulationConfig
    x_m: np.ndarray
    y_m: np.ndarray
    z_m: np.ndarray
    conductivity_w_mk: np.ndarray
    heat_w: np.ndarray
    temperature_k: np.ndarray
    iterations: int
    converged: bool
    max_delta_k: float
    component_reports: list[ComponentReport]
    x_edges_m: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    y_edges_m: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    z_edges_m: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    diagnostics: dict[str, float | int | list[int]] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        return {
            "grid_shape": list(self.temperature_k.shape),
            "iterations": self.iterations,
            "converged": self.converged,
            "max_delta_k": self.max_delta_k,
            "min_temperature_k": float(np.min(self.temperature_k)),
            "max_temperature_k": float(np.max(self.temperature_k)),
            "mean_temperature_k": float(np.mean(self.temperature_k)),
            "component_reports": [asdict(report) for report in self.component_reports],
            "diagnostics": self.diagnostics,
        }


def _mm_to_m(value_mm: float) -> float:
    return value_mm * 1e-3


def _axis_edges(length_m: float, requested_step_m: float) -> np.ndarray:
    cells = max(1, int(np.ceil(length_m / requested_step_m)))
    return np.linspace(0.0, length_m, cells + 1, dtype=float)


def _centers_and_widths(edges_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    widths = np.diff(edges_m)
    centers = 0.5 * (edges_m[:-1] + edges_m[1:])
    return centers, widths


def _unique_sorted_planes(planes_m: list[float], thickness_m: float) -> np.ndarray:
    clipped = [min(max(plane, 0.0), thickness_m) for plane in planes_m]
    clipped.extend([0.0, thickness_m])
    sorted_planes = sorted(clipped)
    unique: list[float] = []
    for plane in sorted_planes:
        if not unique or abs(plane - unique[-1]) > EPS_M:
            unique.append(plane)
    return np.asarray(unique, dtype=float)


def _z_edges(board: Board, layers: list[Layer], components: list[Component]) -> np.ndarray:
    thickness_m = _mm_to_m(board.thickness_mm)
    target_dz_m = _mm_to_m(board.dz_mm)
    planes_m: list[float] = [0.0, thickness_m]

    for layer in layers:
        planes_m.append(_mm_to_m(layer.z_start_mm))
        planes_m.append(_mm_to_m(layer.z_end_mm))

    for component in components:
        depth_mm = component.heat_depth_mm if component.heat_depth_mm is not None else board.dz_mm
        depth_m = min(max(_mm_to_m(depth_mm), EPS_M), thickness_m)
        if component.heat_application == "top":
            planes_m.append(thickness_m - depth_m)
        elif component.heat_application == "bottom":
            planes_m.append(depth_m)

    base_planes = _unique_sorted_planes(planes_m, thickness_m)
    edges: list[float] = [float(base_planes[0])]
    for start, end in zip(base_planes[:-1], base_planes[1:]):
        width = float(end - start)
        if width <= EPS_M:
            continue
        splits = max(1, int(np.ceil(width / target_dz_m)))
        segment = np.linspace(start, end, splits + 1, dtype=float)
        edges.extend(float(value) for value in segment[1:])
    return np.asarray(edges, dtype=float)


def _build_grid(board: Board, layers: list[Layer], components: list[Component]) -> Grid:
    x_edges_m = _axis_edges(_mm_to_m(board.length_mm), _mm_to_m(board.dx_mm))
    y_edges_m = _axis_edges(_mm_to_m(board.width_mm), _mm_to_m(board.dy_mm))
    z_edges_m = _z_edges(board, layers, components)
    x_m, dx_m = _centers_and_widths(x_edges_m)
    y_m, dy_m = _centers_and_widths(y_edges_m)
    z_m, dz_m = _centers_and_widths(z_edges_m)
    return Grid(x_edges_m, y_edges_m, z_edges_m, x_m, y_m, z_m, dx_m, dy_m, dz_m)


def _validate_config(config: SimulationConfig) -> None:
    board = config.board
    for name, value in asdict(board).items():
        if value <= 0.0:
            raise ValueError(f"board.{name} must be > 0.")
    if not config.layers:
        raise ValueError("At least one PCB layer is required.")
    for layer in config.layers:
        if layer.z_start_mm < 0.0 or layer.z_end_mm <= layer.z_start_mm:
            raise ValueError(f"Layer '{layer.name}' has invalid z extents.")
        if layer.z_end_mm > board.thickness_mm:
            raise ValueError(f"Layer '{layer.name}' extends beyond board thickness.")
        if layer.conductivity_w_mk <= 0.0:
            raise ValueError(f"Layer '{layer.name}' conductivity must be > 0.")
    for component in config.components:
        if component.power_w < 0.0:
            raise ValueError(f"Component '{component.name}' power must be >= 0.")
        if component.width_mm <= 0.0 or component.depth_mm <= 0.0:
            raise ValueError(f"Component '{component.name}' footprint dimensions must be > 0.")
        if component.height_mm <= 0.0:
            raise ValueError(f"Component '{component.name}' height must be > 0.")
        if component.steady_state_thermal_resistance_k_per_w <= 0.0:
            raise ValueError(f"Component '{component.name}' thermal resistance must be > 0.")
        if component.x_mm < 0.0 or component.y_mm < 0.0:
            raise ValueError(f"Component '{component.name}' position must be inside the PCB.")
        if component.x_mm + component.width_mm > board.length_mm:
            raise ValueError(f"Component '{component.name}' extends beyond board length.")
        if component.y_mm + component.depth_mm > board.width_mm:
            raise ValueError(f"Component '{component.name}' extends beyond board width.")
    boundary = config.boundary
    if boundary.convection_coefficient_w_m2k < 0.0:
        raise ValueError("Convection coefficient must be >= 0.")
    if boundary.emissivity < 0.0 or boundary.emissivity > 1.0:
        raise ValueError("Emissivity must be in [0, 1].")
    solver = config.solver
    if solver.relaxation_factor <= 0.0 or solver.relaxation_factor >= 2.0:
        raise ValueError("Relaxation factor must be in (0, 2).")
    if solver.tolerance_k <= 0.0 or solver.max_iterations <= 0:
        raise ValueError("Solver tolerance and max_iterations must be positive.")
    if solver.radiation_outer_iterations <= 0:
        raise ValueError("Radiation outer iterations must be positive.")
    if solver.radiation_tolerance_k <= 0.0:
        raise ValueError("Radiation tolerance must be positive.")


def component_equivalent_conductivity_w_mk(component: Component) -> float:
    """Convert user-entered steady-state Rth to equivalent component conductivity.

    Version3 reports this value for traceability, but the default solve no longer
    applies it as PCB-cell conductivity. Rth is used for junction-rise reporting.
    """

    height_m = _mm_to_m(component.height_mm)
    length_m = _mm_to_m(component.width_mm)
    width_m = _mm_to_m(component.depth_mm)
    return height_m / (
        component.steady_state_thermal_resistance_k_per_w * length_m * width_m
    )


def _layer_property_field(layers: list[Layer], grid: Grid) -> np.ndarray:
    conductivity = np.full(
        (len(grid.x_m), len(grid.y_m), len(grid.z_m)),
        layers[0].conductivity_w_mk,
        dtype=float,
    )
    z0 = grid.z_edges_m[:-1]
    z1 = grid.z_edges_m[1:]
    for layer in layers[1:]:
        start_m = _mm_to_m(layer.z_start_mm)
        end_m = _mm_to_m(layer.z_end_mm)
        layer_z_mask = (z1 > start_m + EPS_M) & (z0 < end_m - EPS_M)
        conductivity[:, :, layer_z_mask] = layer.conductivity_w_mk
    return conductivity


def _apply_vias(conductivity: np.ndarray, grid: Grid, vias: list[ThermalVia]) -> None:
    x = grid.x_m[:, None]
    y = grid.y_m[None, :]
    z0 = grid.z_edges_m[:-1]
    z1 = grid.z_edges_m[1:]
    for via in vias:
        radius_m = 0.5 * _mm_to_m(via.diameter_mm)
        z_start = _mm_to_m(via.z_start_mm)
        z_end = _mm_to_m(via.z_end_mm)
        for ix in range(max(1, via.count_x)):
            for iy in range(max(1, via.count_y)):
                center_x = _mm_to_m(via.x_mm + ix * via.pitch_x_mm)
                center_y = _mm_to_m(via.y_mm + iy * via.pitch_y_mm)
                xy_mask = (x - center_x) ** 2 + (y - center_y) ** 2 <= radius_m**2
                z_mask = (z1 > z_start + EPS_M) & (z0 < z_end - EPS_M)
                mask = xy_mask[:, :, None] & z_mask[None, None, :]
                conductivity[mask] = np.maximum(conductivity[mask], via.conductivity_w_mk)


def _overlap_1d(edges_m: np.ndarray, start_m: float, end_m: float) -> np.ndarray:
    return np.maximum(0.0, np.minimum(edges_m[1:], end_m) - np.maximum(edges_m[:-1], start_m))


def _component_source_weights(component: Component, grid: Grid) -> np.ndarray:
    x0 = _mm_to_m(component.x_mm)
    x1 = _mm_to_m(component.x_mm + component.width_mm)
    y0 = _mm_to_m(component.y_mm)
    y1 = _mm_to_m(component.y_mm + component.depth_mm)
    xy_weights = _overlap_1d(grid.x_edges_m, x0, x1)[:, None] * _overlap_1d(
        grid.y_edges_m, y0, y1
    )[None, :]

    z_weights = np.zeros(len(grid.z_m), dtype=float)
    if component.heat_application == "top":
        z_weights[-1] = 1.0
    elif component.heat_application == "bottom":
        z_weights[0] = 1.0
    elif component.heat_application == "full_thickness":
        z_weights = grid.dz_m / float(np.sum(grid.dz_m))
    else:
        raise ValueError(f"Unknown heat_application '{component.heat_application}'.")

    return xy_weights[:, :, None] * z_weights[None, None, :]


def _build_heat_field(
    config: SimulationConfig,
    grid: Grid,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    heat = np.zeros((len(grid.x_m), len(grid.y_m), len(grid.z_m)), dtype=float)
    weights_by_component: dict[str, np.ndarray] = {}
    for component in config.components:
        weights = _component_source_weights(component, grid)
        total_weight = float(np.sum(weights))
        if total_weight <= 0.0:
            raise ValueError(
                f"Component '{component.name}' does not overlap any grid cells. "
                "Check its footprint and board location."
            )
        heat += component.power_w * weights / total_weight
        weights_by_component[component.name] = weights
    return heat, weights_by_component


def _radiation_coefficient(
    temperature_k: float | np.ndarray,
    surrounding_temperature_k: float,
    emissivity: float,
) -> float | np.ndarray:
    return emissivity * SIGMA_W_M2K4 * (
        temperature_k + surrounding_temperature_k
    ) * (np.asarray(temperature_k) ** 2 + surrounding_temperature_k**2)


def _face_conductance(
    k0: np.ndarray,
    k1: np.ndarray,
    area_m2: np.ndarray,
    distance_m: np.ndarray,
) -> np.ndarray:
    harmonic_k = np.divide(
        2.0 * k0 * k1,
        k0 + k1,
        out=np.zeros_like(k0, dtype=float),
        where=(k0 > 0.0) & (k1 > 0.0) & ((k0 + k1) > 0.0),
    )
    return harmonic_k * area_m2 / distance_m


def _add_symmetric_face_entries(
    off_rows: list[np.ndarray],
    off_cols: list[np.ndarray],
    off_data: list[np.ndarray],
    diag: np.ndarray,
    rows: np.ndarray,
    cols: np.ndarray,
    conductance: np.ndarray,
) -> None:
    rows_flat = rows.ravel()
    cols_flat = cols.ravel()
    g_flat = conductance.ravel()
    np.add.at(diag, rows_flat, g_flat)
    np.add.at(diag, cols_flat, g_flat)
    off_rows.extend([rows_flat, cols_flat])
    off_cols.extend([cols_flat, rows_flat])
    off_data.extend([-g_flat, -g_flat])


def _add_boundary(
    diag: np.ndarray,
    rhs: np.ndarray,
    rows: np.ndarray,
    area_m2: np.ndarray,
    temperature_reference_k: np.ndarray | float,
    config: SimulationConfig,
) -> None:
    rows_flat = rows.ravel()
    area_flat = area_m2.ravel()
    temp_ref_flat = np.broadcast_to(temperature_reference_k, area_m2.shape).ravel()
    g_conv = config.boundary.convection_coefficient_w_m2k * area_flat
    h_rad = _radiation_coefficient(
        temp_ref_flat,
        config.boundary.surrounding_temperature_k,
        config.boundary.emissivity,
    )
    g_rad = h_rad * area_flat
    np.add.at(diag, rows_flat, g_conv + g_rad)
    np.add.at(
        rhs,
        rows_flat,
        g_conv * config.boundary.ambient_temperature_k
        + g_rad * config.boundary.surrounding_temperature_k,
    )


def _assemble_sparse_system(
    config: SimulationConfig,
    grid: Grid,
    conductivity: np.ndarray,
    heat_w: np.ndarray,
    radiation_temperature_k: np.ndarray | None,
) -> tuple[sparse.csr_matrix, np.ndarray]:
    nx, ny, nz = conductivity.shape
    cell_count = nx * ny * nz
    index = np.arange(cell_count, dtype=np.int64).reshape((nx, ny, nz))
    diag = np.zeros(cell_count, dtype=float)
    rhs = heat_w.reshape(cell_count).astype(float).copy()
    off_rows: list[np.ndarray] = []
    off_cols: list[np.ndarray] = []
    off_data: list[np.ndarray] = []

    if nx > 1:
        area = grid.dy_m[None, :, None] * grid.dz_m[None, None, :]
        distance = 0.5 * (grid.dx_m[:-1, None, None] + grid.dx_m[1:, None, None])
        conductance = _face_conductance(
            conductivity[:-1, :, :],
            conductivity[1:, :, :],
            np.broadcast_to(area, (nx - 1, ny, nz)),
            np.broadcast_to(distance, (nx - 1, ny, nz)),
        )
        _add_symmetric_face_entries(
            off_rows, off_cols, off_data, diag, index[:-1, :, :], index[1:, :, :], conductance
        )

    if ny > 1:
        area = grid.dx_m[:, None, None] * grid.dz_m[None, None, :]
        distance = 0.5 * (grid.dy_m[None, :-1, None] + grid.dy_m[None, 1:, None])
        conductance = _face_conductance(
            conductivity[:, :-1, :],
            conductivity[:, 1:, :],
            np.broadcast_to(area, (nx, ny - 1, nz)),
            np.broadcast_to(distance, (nx, ny - 1, nz)),
        )
        _add_symmetric_face_entries(
            off_rows, off_cols, off_data, diag, index[:, :-1, :], index[:, 1:, :], conductance
        )

    if nz > 1:
        area = grid.dx_m[:, None, None] * grid.dy_m[None, :, None]
        distance = 0.5 * (grid.dz_m[None, None, :-1] + grid.dz_m[None, None, 1:])
        conductance = _face_conductance(
            conductivity[:, :, :-1],
            conductivity[:, :, 1:],
            np.broadcast_to(area, (nx, ny, nz - 1)),
            np.broadcast_to(distance, (nx, ny, nz - 1)),
        )
        _add_symmetric_face_entries(
            off_rows, off_cols, off_data, diag, index[:, :, :-1], index[:, :, 1:], conductance
        )

    temp_ref = radiation_temperature_k
    scalar_temp_ref = config.solver.initial_temperature_k if temp_ref is None else None
    yz_area = grid.dy_m[:, None] * grid.dz_m[None, :]
    xz_area = grid.dx_m[:, None] * grid.dz_m[None, :]
    xy_area = grid.dx_m[:, None] * grid.dy_m[None, :]

    _add_boundary(
        diag,
        rhs,
        index[0, :, :],
        yz_area,
        scalar_temp_ref if temp_ref is None else temp_ref[0, :, :],
        config,
    )
    _add_boundary(
        diag,
        rhs,
        index[-1, :, :],
        yz_area,
        scalar_temp_ref if temp_ref is None else temp_ref[-1, :, :],
        config,
    )
    _add_boundary(
        diag,
        rhs,
        index[:, 0, :],
        xz_area,
        scalar_temp_ref if temp_ref is None else temp_ref[:, 0, :],
        config,
    )
    _add_boundary(
        diag,
        rhs,
        index[:, -1, :],
        xz_area,
        scalar_temp_ref if temp_ref is None else temp_ref[:, -1, :],
        config,
    )
    _add_boundary(
        diag,
        rhs,
        index[:, :, 0],
        xy_area,
        scalar_temp_ref if temp_ref is None else temp_ref[:, :, 0],
        config,
    )
    _add_boundary(
        diag,
        rhs,
        index[:, :, -1],
        xy_area,
        scalar_temp_ref if temp_ref is None else temp_ref[:, :, -1],
        config,
    )

    all_rows = np.concatenate([*off_rows, np.arange(cell_count, dtype=np.int64)])
    all_cols = np.concatenate([*off_cols, np.arange(cell_count, dtype=np.int64)])
    all_data = np.concatenate([*off_data, diag])
    matrix = sparse.coo_matrix((all_data, (all_rows, all_cols)), shape=(cell_count, cell_count))
    return matrix.tocsr(), rhs


def _component_reports(
    config: SimulationConfig,
    temperature: np.ndarray,
    component_weights: dict[str, np.ndarray],
) -> list[ComponentReport]:
    reports: list[ComponentReport] = []
    for component in config.components:
        weights = component_weights[component.name]
        mask = weights > 0.0
        local_t = temperature[mask]
        local_w = weights[mask]
        max_board_t = float(np.max(local_t))
        average_board_t = float(np.sum(local_t * local_w) / np.sum(local_w))
        junction_rise_k = component.power_w * component.steady_state_thermal_resistance_k_per_w
        reports.append(
            ComponentReport(
                name=component.name,
                board_average_temperature_k=average_board_t,
                board_max_temperature_k=max_board_t,
                estimated_junction_temperature_k=max_board_t + junction_rise_k,
                equivalent_thermal_conductivity_w_mk=component_equivalent_conductivity_w_mk(
                    component
                ),
                occupied_cell_count=int(np.sum(mask)),
                junction_rise_k=float(junction_rise_k),
            )
        )
    return reports


def _solve_sparse_system(
    matrix: sparse.csr_matrix,
    rhs: np.ndarray,
    config: SimulationConfig,
) -> tuple[np.ndarray, int, bool, float]:
    if matrix.shape[0] <= DIRECT_SOLVE_CELL_LIMIT:
        solution = sparse_linalg.spsolve(matrix, rhs)
        residual = matrix @ solution - rhs
        max_residual = float(np.max(np.abs(residual)))
        converged = bool(np.all(np.isfinite(solution)) and max_residual < config.solver.tolerance_k)
        return np.asarray(solution, dtype=float), 1, converged, max_residual

    iterations = 0

    def count_iteration(_: np.ndarray) -> None:
        nonlocal iterations
        iterations += 1

    # Use a lightweight ILU: low fill_factor and aggressive drop_tol so the
    # preconditioner build stays fast and fits in memory on constrained servers.
    # Fall back to diagonal (Jacobi) if ILU fails for any reason.
    n = matrix.shape[0]
    fill = 3 if n > 50_000 else 6
    drop = 1e-2 if n > 50_000 else 1e-3
    try:
        ilu = sparse_linalg.spilu(matrix.tocsc(), drop_tol=drop, fill_factor=fill)
        preconditioner = sparse_linalg.LinearOperator(matrix.shape, ilu.solve)
    except Exception:
        diagonal = matrix.diagonal()
        inverse_diagonal = np.divide(
            1.0,
            diagonal,
            out=np.zeros_like(diagonal),
            where=diagonal != 0.0,
        )
        preconditioner = sparse.diags(inverse_diagonal, format="csr")
    initial = np.full_like(rhs, config.solver.initial_temperature_k, dtype=float)
    solution, info = sparse_linalg.cg(
        matrix,
        rhs,
        x0=initial,
        rtol=max(1e-10, min(1e-4, config.solver.tolerance_k)),
        atol=config.solver.tolerance_k,
        maxiter=config.solver.max_iterations,
        M=preconditioner,
        callback=count_iteration,
    )
    residual = matrix @ solution - rhs
    max_residual = float(np.max(np.abs(residual)))
    converged = bool(info == 0 and np.all(np.isfinite(solution)))
    return np.asarray(solution, dtype=float), iterations, converged, max_residual


def _boundary_loss_w(
    config: SimulationConfig,
    grid: Grid,
    temperature: np.ndarray,
    radiation_temperature_k: np.ndarray | None,
    exact_radiation: bool,
) -> float:
    h = config.boundary.convection_coefficient_w_m2k
    ambient = config.boundary.ambient_temperature_k
    surrounding = config.boundary.surrounding_temperature_k
    emissivity = config.boundary.emissivity

    def face_loss(
        temp_face: np.ndarray,
        area_m2: np.ndarray,
        temp_ref_face: np.ndarray | float,
    ) -> float:
        conv = h * area_m2 * (temp_face - ambient)
        if exact_radiation:
            rad = emissivity * SIGMA_W_M2K4 * area_m2 * (temp_face**4 - surrounding**4)
        else:
            h_rad = _radiation_coefficient(temp_ref_face, surrounding, emissivity)
            rad = h_rad * area_m2 * (temp_face - surrounding)
        return float(np.sum(conv + rad))

    yz_area = grid.dy_m[:, None] * grid.dz_m[None, :]
    xz_area = grid.dx_m[:, None] * grid.dz_m[None, :]
    xy_area = grid.dx_m[:, None] * grid.dy_m[None, :]
    scalar_ref = config.solver.initial_temperature_k if radiation_temperature_k is None else None
    return sum(
        [
            face_loss(
                temperature[0, :, :],
                yz_area,
                scalar_ref if radiation_temperature_k is None else radiation_temperature_k[0, :, :],
            ),
            face_loss(
                temperature[-1, :, :],
                yz_area,
                scalar_ref if radiation_temperature_k is None else radiation_temperature_k[-1, :, :],
            ),
            face_loss(
                temperature[:, 0, :],
                xz_area,
                scalar_ref if radiation_temperature_k is None else radiation_temperature_k[:, 0, :],
            ),
            face_loss(
                temperature[:, -1, :],
                xz_area,
                scalar_ref if radiation_temperature_k is None else radiation_temperature_k[:, -1, :],
            ),
            face_loss(
                temperature[:, :, 0],
                xy_area,
                scalar_ref if radiation_temperature_k is None else radiation_temperature_k[:, :, 0],
            ),
            face_loss(
                temperature[:, :, -1],
                xy_area,
                scalar_ref if radiation_temperature_k is None else radiation_temperature_k[:, :, -1],
            ),
        ]
    )


def solve_steady_state(config: SimulationConfig) -> SimulationResult:
    """Solve the PCB steady-state temperature field as a sparse finite-volume system."""

    _validate_config(config)
    grid = _build_grid(config.board, config.layers, config.components)
    conductivity = _layer_property_field(config.layers, grid)
    _apply_vias(conductivity, grid, config.thermal_vias)
    heat_w, component_weights = _build_heat_field(config, grid)

    total_iterations = 0
    max_delta = float("inf")
    converged = False
    matrix_nonzeros = 0
    solution: np.ndarray | None = None
    previous_temperature: np.ndarray | None = None
    final_radiation_temperature: np.ndarray | None = None
    outer_used = 0

    for outer_index in range(config.solver.radiation_outer_iterations):
        radiation_temperature = previous_temperature
        final_radiation_temperature = radiation_temperature
        matrix, rhs = _assemble_sparse_system(config, grid, conductivity, heat_w, radiation_temperature)
        matrix_nonzeros = int(matrix.nnz)
        flat_solution, iterations, linear_converged, max_delta = _solve_sparse_system(
            matrix, rhs, config
        )
        total_iterations += iterations
        temperature = flat_solution.reshape(conductivity.shape)
        outer_used = outer_index + 1
        if previous_temperature is None:
            nonlinear_delta = float("inf")
        else:
            nonlinear_delta = float(np.max(np.abs(temperature - previous_temperature)))
        solution = temperature
        if config.solver.radiation_outer_iterations == 1:
            converged = linear_converged
            break
        converged = linear_converged and nonlinear_delta <= config.solver.radiation_tolerance_k
        if converged:
            break
        converged = False
        previous_temperature = temperature

    if solution is None:
        raise RuntimeError("Solver failed to produce a solution.")

    total_power_w = float(np.sum(heat_w))
    boundary_loss_w = _boundary_loss_w(
        config,
        grid,
        solution,
        final_radiation_temperature,
        exact_radiation=False,
    )
    exact_boundary_loss_w = _boundary_loss_w(
        config,
        grid,
        solution,
        final_radiation_temperature,
        exact_radiation=True,
    )
    diagnostics: dict[str, float | int | list[int]] = {
        "cell_count": int(np.prod(solution.shape)),
        "grid_shape": [int(value) for value in solution.shape],
        "matrix_nonzeros": matrix_nonzeros,
        "total_power_w": total_power_w,
        "boundary_loss_w": boundary_loss_w,
        "energy_balance_error_w": total_power_w - boundary_loss_w,
        "exact_radiation_boundary_loss_w": exact_boundary_loss_w,
        "exact_radiation_balance_error_w": total_power_w - exact_boundary_loss_w,
        "radiation_outer_iterations_used": outer_used,
        "min_dx_mm": float(np.min(grid.dx_m) * 1000.0),
        "max_dx_mm": float(np.max(grid.dx_m) * 1000.0),
        "min_dy_mm": float(np.min(grid.dy_m) * 1000.0),
        "max_dy_mm": float(np.max(grid.dy_m) * 1000.0),
        "min_dz_mm": float(np.min(grid.dz_m) * 1000.0),
        "max_dz_mm": float(np.max(grid.dz_m) * 1000.0),
    }

    return SimulationResult(
        config=config,
        x_m=grid.x_m,
        y_m=grid.y_m,
        z_m=grid.z_m,
        x_edges_m=grid.x_edges_m,
        y_edges_m=grid.y_edges_m,
        z_edges_m=grid.z_edges_m,
        conductivity_w_mk=conductivity,
        heat_w=heat_w,
        temperature_k=solution,
        iterations=total_iterations,
        converged=converged,
        max_delta_k=max_delta,
        component_reports=_component_reports(config, solution, component_weights),
        diagnostics=diagnostics,
    )
