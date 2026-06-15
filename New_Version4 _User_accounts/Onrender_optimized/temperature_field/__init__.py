"""3D steady-state PCB temperature field generator."""

from .models import (
    Board,
    BoundaryCondition,
    Component,
    Layer,
    SimulationConfig,
    SolverSettings,
    ThermalVia,
)
from .solver import (
    SimulationResult,
    component_equivalent_conductivity_w_mk,
    solve_steady_state,
)
from .thermal_resistance import estimate_steady_state_resistance

__all__ = [
    "Board",
    "BoundaryCondition",
    "Component",
    "Layer",
    "SimulationConfig",
    "SimulationResult",
    "SolverSettings",
    "ThermalVia",
    "component_equivalent_conductivity_w_mk",
    "estimate_steady_state_resistance",
    "solve_steady_state",
]
