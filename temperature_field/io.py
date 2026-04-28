from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .models import (
    Board,
    BoundaryCondition,
    Component,
    Layer,
    SimulationConfig,
    SolverSettings,
    ThermalVia,
)
from .solver import SimulationResult
from .thermal_resistance import estimate_steady_state_resistance


def _read_curve_csv(path: Path) -> tuple[list[float], list[float]]:
    times: list[float] = []
    values: list[float] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if "time_s" not in reader.fieldnames or "zth_k_per_w" not in reader.fieldnames:
            raise ValueError("Curve CSV must contain time_s and zth_k_per_w columns.")
        for row in reader:
            times.append(float(row["time_s"]))
            values.append(float(row["zth_k_per_w"]))
    return times, values


def _component_from_payload(payload: dict[str, Any], base_dir: Path) -> Component:
    payload = dict(payload)
    if "steady_state_thermal_resistance_k_per_w" not in payload:
        curve = payload.pop("transient_thermal_impedance_curve", None)
        if curve is None:
            raise ValueError(
                f"Component '{payload.get('name', '<unnamed>')}' needs either "
                "steady_state_thermal_resistance_k_per_w or transient_thermal_impedance_curve."
            )
        if isinstance(curve, str):
            times, values = _read_curve_csv(base_dir / curve)
        else:
            times = [point["time_s"] for point in curve]
            values = [point["zth_k_per_w"] for point in curve]
        payload["steady_state_thermal_resistance_k_per_w"] = estimate_steady_state_resistance(
            times, values
        )
    return Component(**payload)


def load_config(path: str | Path) -> SimulationConfig:
    config_path = Path(path)
    payload = json.loads(config_path.read_text())
    base_dir = config_path.parent
    return SimulationConfig(
        board=Board(**payload["board"]),
        boundary=BoundaryCondition(**payload.get("boundary", {})),
        solver=SolverSettings(**payload.get("solver", {})),
        layers=[Layer(**layer) for layer in payload.get("layers", [])],
        components=[
            _component_from_payload(component, base_dir)
            for component in payload.get("components", [])
        ],
        thermal_vias=[ThermalVia(**via) for via in payload.get("thermal_vias", [])],
    )


def save_summary(result: SimulationResult, path: str | Path) -> None:
    Path(path).write_text(json.dumps(result.summary(), indent=2))


def save_npz(result: SimulationResult, path: str | Path) -> None:
    np.savez_compressed(
        path,
        x_m=result.x_m,
        y_m=result.y_m,
        z_m=result.z_m,
        x_edges_m=result.x_edges_m,
        y_edges_m=result.y_edges_m,
        z_edges_m=result.z_edges_m,
        temperature_k=result.temperature_k,
        conductivity_w_mk=result.conductivity_w_mk,
        heat_w=result.heat_w,
        config_json=json.dumps(asdict(result.config)),
        summary_json=json.dumps(result.summary()),
    )
