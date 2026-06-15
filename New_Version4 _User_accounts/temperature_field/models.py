from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ThermalResistanceMode = Literal[
    "junction_to_ambient",
    "junction_to_case_to_ambient",
    "junction_to_board",
    "junction_to_measured_case",
    "junction_to_case_to_board",
    "junction_to_board_to_ambient",
]


@dataclass(frozen=True)
class Board:
    length_mm: float
    width_mm: float
    thickness_mm: float
    dx_mm: float
    dy_mm: float
    dz_mm: float


@dataclass(frozen=True)
class BoundaryCondition:
    ambient_temperature_k: float = 300.0
    surrounding_temperature_k: float = 300.0
    convection_coefficient_w_m2k: float = 13.0
    emissivity: float = 0.8


@dataclass(frozen=True)
class SolverSettings:
    initial_temperature_k: float = 300.0
    relaxation_factor: float = 1.2
    tolerance_k: float = 1e-6
    max_iterations: int = 25_000
    radiation_outer_iterations: int = 1
    radiation_tolerance_k: float = 0.05


@dataclass(frozen=True)
class Layer:
    name: str
    z_start_mm: float
    z_end_mm: float
    conductivity_w_mk: float


@dataclass(frozen=True)
class Component:
    name: str
    x_mm: float
    y_mm: float
    width_mm: float
    depth_mm: float
    height_mm: float
    power_w: float
    steady_state_thermal_resistance_k_per_w: float
    thermal_resistance_mode: ThermalResistanceMode = "junction_to_ambient"
    secondary_thermal_resistance_k_per_w: float | None = None
    case_to_ambient_thermal_resistance_k_per_w: float | None = None
    reference_temperature_k: float | None = None
    z_mm: float = 0.0
    heat_application: Literal["top", "bottom", "full_thickness"] = "top"
    heat_depth_mm: float | None = None


@dataclass(frozen=True)
class ThermalVia:
    name: str
    x_mm: float
    y_mm: float
    diameter_mm: float
    z_start_mm: float
    z_end_mm: float
    conductivity_w_mk: float = 385.0
    count_x: int = 1
    count_y: int = 1
    pitch_x_mm: float = 0.0
    pitch_y_mm: float = 0.0


@dataclass(frozen=True)
class SimulationConfig:
    board: Board
    boundary: BoundaryCondition = field(default_factory=BoundaryCondition)
    solver: SolverSettings = field(default_factory=SolverSettings)
    layers: list[Layer] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    thermal_vias: list[ThermalVia] = field(default_factory=list)
