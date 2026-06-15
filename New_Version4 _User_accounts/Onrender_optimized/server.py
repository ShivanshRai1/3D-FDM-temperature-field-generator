from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np

from temperature_field.models import (
    Board,
    BoundaryCondition,
    Component,
    Layer,
    SimulationConfig,
    SolverSettings,
    ThermalVia,
)
from temperature_field.solver import solve_steady_state


ROOT = Path(__file__).resolve().parent
RUN_MANIFEST_DIR = ROOT / "temp" / "simulation_runs"
RENDER_FREE_MAX_CELLS = int(os.environ.get("RENDER_FREE_MAX_CELLS", "75000"))
RENDER_FREE_MIN_DX_MM = float(os.environ.get("RENDER_FREE_MIN_DX_MM", "1.0"))
RENDER_FREE_MIN_DY_MM = float(os.environ.get("RENDER_FREE_MIN_DY_MM", "1.0"))
RENDER_FREE_MIN_DZ_MM = float(os.environ.get("RENDER_FREE_MIN_DZ_MM", "0.1"))
RENDER_FREE_MAX_RADIATION_ITERATIONS = int(
    os.environ.get("RENDER_FREE_MAX_RADIATION_ITERATIONS", "12")
)
RENDER_FREE_MAX_SOLVER_JOBS = int(os.environ.get("RENDER_FREE_MAX_SOLVER_JOBS", "1"))
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
ACTIVE_SOLVER_JOBS = 0
ACTIVE_SOLVER_JOBS_LOCK = threading.Lock()


def _float(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    if value is None or value == "":
        return default
    return float(value)


def _component_rth_mode(component: dict[str, Any]) -> str:
    mode = str(
        component.get("thermal_resistance_mode", component.get("rth_mode", "junction_to_ambient"))
    ).strip()
    if mode in {"rth_ja", "ja", "junction-to-ambient"}:
        return "junction_to_ambient"
    if mode in {"rth_jc", "jc", "junction-to-case"}:
        return "junction_to_case"
    if mode not in {"junction_to_ambient", "junction_to_case"}:
        raise ValueError(
            f"Component '{component.get('name', component.get('id', 'component'))}' has unsupported thermal_resistance_mode '{mode}'."
        )
    return mode


def _build_config(payload: dict[str, Any], omega: float) -> SimulationConfig:
    board_payload = payload["board"]
    length_mm = _float(board_payload, "length_mm", 40.0)
    width_mm = _float(board_payload, "width_mm", 30.0)
    thickness_mm = _float(board_payload, "thickness_mm", 1.6)
    dx_mm = _float(board_payload, "dx_mm", max(1.0, min(length_mm, width_mm) / 28.0))
    dy_mm = _float(board_payload, "dy_mm", dx_mm)
    dz_mm = _float(board_payload, "dz_mm", max(0.1, thickness_mm / 4.0))

    board = Board(
        length_mm=length_mm,
        width_mm=width_mm,
        thickness_mm=thickness_mm,
        dx_mm=dx_mm,
        dy_mm=dy_mm,
        dz_mm=dz_mm,
    )

    layers = [
        Layer(
            name="FR4 core",
            z_start_mm=0.0,
            z_end_mm=thickness_mm,
            conductivity_w_mk=0.35,
        )
    ]
    for layer in payload.get("copper_layers", []):
        layers.append(
            Layer(
                name=str(layer.get("name", layer.get("id", "copper"))),
                z_start_mm=max(0.0, _float(layer, "z_start_mm", 0.0)),
                z_end_mm=min(thickness_mm, _float(layer, "z_end_mm", thickness_mm)),
                conductivity_w_mk=_float(layer, "conductivity_w_mk", 385.0),
            )
        )

    components = []
    for component in payload.get("components", []):
        rth_mode = _component_rth_mode(component)
        components.append(
            Component(
                name=str(component.get("name", component.get("id", "component"))),
                x_mm=_float(component, "x_mm", 0.0),
                y_mm=_float(component, "y_mm", 0.0),
                z_mm=thickness_mm,
                width_mm=_float(component, "width_mm", 1.0),
                depth_mm=_float(component, "depth_mm", 1.0),
                height_mm=_float(component, "height_mm", 0.5),
                power_w=_float(component, "power_w", 0.0),
                steady_state_thermal_resistance_k_per_w=_float(
                    component, "steady_state_thermal_resistance_k_per_w", 1.0
                ),
                thermal_resistance_mode=rth_mode,
                case_to_ambient_thermal_resistance_k_per_w=(
                    _float(component, "case_to_ambient_thermal_resistance_k_per_w", 0.0)
                    if rth_mode == "junction_to_case"
                    else None
                ),
                heat_application="top",
                heat_depth_mm=dz_mm,
            )
        )

    vias = []
    for via in payload.get("thermal_vias", []):
        vias.append(
            ThermalVia(
                name=str(via.get("id", "via")),
                x_mm=_float(via, "x_mm", 0.0),
                y_mm=_float(via, "y_mm", 0.0),
                diameter_mm=_float(via, "diameter_mm", 0.3),
                z_start_mm=max(0.0, _float(via, "z_start_mm", 0.0)),
                z_end_mm=min(thickness_mm, _float(via, "z_end_mm", thickness_mm)),
                conductivity_w_mk=_float(via, "conductivity_w_mk", 385.0),
            )
        )

    boundary_payload = payload.get("boundary", {})
    boundary = BoundaryCondition(
        ambient_temperature_k=_float(boundary_payload, "ambient_temperature_k", 300.0),
        surrounding_temperature_k=_float(boundary_payload, "surrounding_temperature_k", 300.0),
        convection_coefficient_w_m2k=_float(
            boundary_payload, "convection_coefficient_w_m2k", 13.0
        ),
        emissivity=_float(boundary_payload, "emissivity", 0.8),
    )

    solver = SolverSettings(
        initial_temperature_k=boundary.ambient_temperature_k,
        relaxation_factor=omega,
        tolerance_k=float(payload.get("solver_tolerance_k", 1e-4)),
        max_iterations=int(payload.get("solver_max_iterations", 20_000)),
        radiation_outer_iterations=int(payload.get("radiation_outer_iterations", 8)),
        radiation_tolerance_k=float(payload.get("radiation_tolerance_k", 0.05)),
    )

    return SimulationConfig(
        board=board,
        boundary=boundary,
        solver=solver,
        layers=layers,
        components=components,
        thermal_vias=vias,
    )


def _validate_render_free_limits(payload: dict[str, Any]) -> None:
    board_payload = payload.get("board", {})
    length_mm = _float(board_payload, "length_mm", 40.0)
    width_mm = _float(board_payload, "width_mm", 30.0)
    thickness_mm = _float(board_payload, "thickness_mm", 1.6)
    dx_mm = _float(board_payload, "dx_mm", 2.0)
    dy_mm = _float(board_payload, "dy_mm", dx_mm)
    dz_mm = _float(board_payload, "dz_mm", 0.2)
    radiation_iterations = int(payload.get("radiation_outer_iterations", 8))

    problems: list[str] = []
    if dx_mm < RENDER_FREE_MIN_DX_MM:
        problems.append(f"dx must be at least {RENDER_FREE_MIN_DX_MM:g} mm on Render Free.")
    if dy_mm < RENDER_FREE_MIN_DY_MM:
        problems.append(f"dy must be at least {RENDER_FREE_MIN_DY_MM:g} mm on Render Free.")
    if dz_mm < RENDER_FREE_MIN_DZ_MM:
        problems.append(f"dz must be at least {RENDER_FREE_MIN_DZ_MM:g} mm on Render Free.")
    if radiation_iterations > RENDER_FREE_MAX_RADIATION_ITERATIONS:
        problems.append(
            "Radiation iterations must be at most "
            f"{RENDER_FREE_MAX_RADIATION_ITERATIONS} on Render Free."
        )

    nx = max(1, int(np.ceil(length_mm / dx_mm)))
    ny = max(1, int(np.ceil(width_mm / dy_mm)))
    nz = max(1, int(np.ceil(thickness_mm / dz_mm)))
    estimated_cells = nx * ny * nz
    if estimated_cells > RENDER_FREE_MAX_CELLS:
        problems.append(
            f"Estimated grid has {estimated_cells:,} cells; Render Free limit is "
            f"{RENDER_FREE_MAX_CELLS:,}. Increase dx/dy/dz."
        )

    if problems:
        raise ValueError(" ".join(problems))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalization_warnings(
    source_config: dict[str, Any], normalized_config: SimulationConfig
) -> list[str]:
    warnings: list[str] = []
    board_payload = source_config.get("board", {})
    checks = [
        ("board.dx_mm", _float(board_payload, "dx_mm", normalized_config.board.dx_mm), normalized_config.board.dx_mm),
        ("board.dy_mm", _float(board_payload, "dy_mm", normalized_config.board.dy_mm), normalized_config.board.dy_mm),
        ("board.dz_mm", _float(board_payload, "dz_mm", normalized_config.board.dz_mm), normalized_config.board.dz_mm),
        (
            "radiation_outer_iterations",
            int(source_config.get("radiation_outer_iterations", normalized_config.solver.radiation_outer_iterations)),
            normalized_config.solver.radiation_outer_iterations,
        ),
        (
            "radiation_tolerance_k",
            float(source_config.get("radiation_tolerance_k", normalized_config.solver.radiation_tolerance_k)),
            normalized_config.solver.radiation_tolerance_k,
        ),
    ]
    for name, requested, normalized in checks:
        if abs(float(requested) - float(normalized)) > 1e-9:
            warnings.append(f"{name} requested {requested} but normalized to {normalized}.")
    return warnings


def _manifest_path(job_id: str) -> Path:
    return RUN_MANIFEST_DIR / f"{job_id}.json"


def _write_run_manifest(job_id: str, payload: dict[str, Any]) -> Path:
    RUN_MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = _manifest_path(job_id)
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)
    return path


def _create_run_manifest(
    job_id: str,
    request: dict[str, Any],
    source_config: dict[str, Any],
    normalized_config: SimulationConfig,
    omega: float,
    mode: str,
) -> Path:
    manifest = {
        "schema": "pcb_thermal_simulation_run_manifest_v1",
        "job_id": job_id,
        "mode": mode,
        "status": "running",
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "omega": omega,
        "raw_request": request,
        "source_config": source_config,
        "normalized_config": asdict(normalized_config),
        "normalization_warnings": _normalization_warnings(source_config, normalized_config),
        "timing": {
            "solver_started_at": None,
            "solver_finished_at": None,
            "solver_wall_time_s": None,
            "response_prepared_at": None,
            "total_wall_time_s": None,
        },
        "result": None,
        "response_payload": None,
        "error": None,
    }
    return _write_run_manifest(job_id, manifest)


def _update_run_manifest(job_id: str, **updates: Any) -> None:
    path = _manifest_path(job_id)
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema": "pcb_thermal_simulation_run_manifest_v1",
            "job_id": job_id,
            "created_at": _utc_now_iso(),
        }
    manifest.update(updates)
    manifest["updated_at"] = _utc_now_iso()
    _write_run_manifest(job_id, manifest)


def _normalize_component_array(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("components")
    if not isinstance(rows, list):
        raise ValueError("Component import payload must contain a 'components' array.")

    default_power_w = float(payload.get("default_power_w", 0.0))
    default_rth = payload.get("default_rth_k_per_w", None)
    default_rth_mode = payload.get("default_rth_mode", "junction_to_ambient")
    default_rth_ca = payload.get("default_rth_ca_k_per_w", None)
    next_index = int(payload.get("next_index", 1))
    normalized: list[dict[str, Any]] = []
    missing_rth: list[str] = []

    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            raise ValueError(f"Component row {row_index} must be an array.")
        if len(row) < 5:
            raise ValueError(
                f"Component row {row_index} must have at least x, y, length, width, and height."
            )

        name_value: Any = None
        rth_value: Any = None
        rth_mode_value: Any = default_rth_mode
        rth_ca_value: Any = default_rth_ca
        power_value: Any = default_power_w
        if len(row) >= 10:
            rth_value = row[5]
            rth_mode_value = row[6]
            rth_ca_value = row[7]
            power_value = row[8]
            name_value = row[9]
        elif len(row) >= 8:
            rth_value = row[5]
            power_value = row[6]
            name_value = row[7]
        elif len(row) == 7:
            rth_value = row[5]
            if isinstance(row[6], str):
                name_value = row[6]
            else:
                power_value = row[6]
        elif len(row) == 6:
            if isinstance(row[5], str):
                name_value = row[5]
            else:
                rth_value = row[5]

        component_id = f"C{next_index + row_index - 1}"
        name = str(name_value).strip() if name_value is not None else component_id
        if not name:
            name = component_id

        rth_missing = rth_value in (None, "")
        if rth_missing:
            fallback_rth = float(default_rth) if default_rth not in (None, "") else 1.0
            rth = max(0.1, fallback_rth)
            missing_rth.append(name)
        else:
            rth = max(0.1, float(rth_value))

        rth_mode = _component_rth_mode({"thermal_resistance_mode": rth_mode_value, "name": name})
        rth_ca_missing = False
        if rth_mode == "junction_to_case":
            rth_ca_missing = rth_ca_value in (None, "")
            if rth_ca_missing:
                missing_rth.append(f"{name} Rth_ca")
                rth_ca = 0.0
            else:
                rth_ca = max(0.0, float(rth_ca_value))
        else:
            rth_ca = None

        normalized.append(
            {
                "id": component_id,
                "name": name,
                "x": float(row[0]),
                "y": float(row[1]),
                "z": None,
                "l": max(0.5, float(row[2])),
                "w": max(0.5, float(row[3])),
                "h": max(0.1, float(row[4])),
                "power": max(0.0, float(power_value)),
                "rth": rth,
                "rthMode": rth_mode,
                "rthCaseToAmbient": rth_ca,
                "rotation": 0,
                "rthMissing": rth_missing or rth_ca_missing,
            }
        )

    return {"components": normalized, "missing_rth": missing_rth}


def _nearest_z_index(z_m: np.ndarray, z_mm: float) -> int:
    return int(np.argmin(np.abs(z_m * 1000.0 - z_mm)))


def _payload_from_result(result, source_config: dict[str, Any]) -> dict[str, Any]:
    temp = result.temperature_k
    top_index = temp.shape[2] - 1
    bottom_index = 0

    views: dict[str, dict[str, Any]] = {
        "top": {
            "name": "top",
            "z": float(result.config.board.thickness_mm + 0.04),
            "nx": int(temp.shape[0]),
            "ny": int(temp.shape[1]),
            "values": temp[:, :, top_index].tolist(),
        },
        "bottom": {
            "name": "bottom",
            "z": -0.04,
            "nx": int(temp.shape[0]),
            "ny": int(temp.shape[1]),
            "values": temp[:, :, bottom_index].tolist(),
        },
    }

    for layer in source_config.get("copper_layers", []):
        layer_id = str(layer.get("id", layer.get("name", "layer")))
        z_center_mm = _float(layer, "z_center_mm", 0.0)
        z_index = _nearest_z_index(result.z_m, z_center_mm)
        views[f"layer:{layer_id}"] = {
            "name": f"layer:{layer_id}",
            "z": float(z_center_mm),
            "nx": int(temp.shape[0]),
            "ny": int(temp.shape[1]),
            "values": temp[:, :, z_index].tolist(),
        }

    summary = result.summary()
    diagnostics = dict(summary.get("diagnostics", {}))
    diagnostics.update(
        {
            "requested_dx_mm": _float(source_config.get("board", {}), "dx_mm", result.config.board.dx_mm),
            "requested_dy_mm": _float(source_config.get("board", {}), "dy_mm", result.config.board.dy_mm),
            "requested_dz_mm": _float(source_config.get("board", {}), "dz_mm", result.config.board.dz_mm),
            "normalized_dx_mm": result.config.board.dx_mm,
            "normalized_dy_mm": result.config.board.dy_mm,
            "normalized_dz_mm": result.config.board.dz_mm,
            "requested_radiation_outer_iterations": int(
                source_config.get(
                    "radiation_outer_iterations",
                    result.config.solver.radiation_outer_iterations,
                )
            ),
            "normalized_radiation_outer_iterations": result.config.solver.radiation_outer_iterations,
            "normalization_warnings": _normalization_warnings(source_config, result.config),
        }
    )
    return {
        "generated_at": "backend",
        "solver": {
            "iterations": int(result.iterations),
            "converged": bool(result.converged),
            "max_delta_k": float(result.max_delta_k),
            "diagnostics": diagnostics,
        },
        "x_mm": (result.x_m * 1000.0).tolist(),
        "y_mm": (result.y_m * 1000.0).tolist(),
        "z_mm": (result.z_m * 1000.0).tolist(),
        "x_edges_mm": (result.x_edges_m * 1000.0).tolist(),
        "y_edges_mm": (result.y_edges_m * 1000.0).tolist(),
        "z_edges_mm": (result.z_edges_m * 1000.0).tolist(),
        "min_temperature_k": summary["min_temperature_k"],
        "max_temperature_k": summary["max_temperature_k"],
        "component_reports": summary["component_reports"],
        "views": views,
    }


def _job_snapshot(job_id: str) -> dict[str, Any]:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return {"status": "missing", "error": "Unknown solver job."}
        snapshot = dict(job)
    snapshot["job_id"] = job_id
    return snapshot


def _set_job(job_id: str, **updates: Any) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(updates)


def _try_acquire_solver_slot() -> bool:
    global ACTIVE_SOLVER_JOBS
    with ACTIVE_SOLVER_JOBS_LOCK:
        if ACTIVE_SOLVER_JOBS >= RENDER_FREE_MAX_SOLVER_JOBS:
            return False
        ACTIVE_SOLVER_JOBS += 1
        return True


def _release_solver_slot() -> None:
    global ACTIVE_SOLVER_JOBS
    with ACTIVE_SOLVER_JOBS_LOCK:
        ACTIVE_SOLVER_JOBS = max(0, ACTIVE_SOLVER_JOBS - 1)


def _run_solver_job(job_id: str, request: dict[str, Any]) -> None:
    if not _try_acquire_solver_slot():
        _set_job(
            job_id,
            status="error",
            message="Solver busy.",
            error="Render Free demo allows only one solver job at a time. Try again after the current run finishes.",
            finished_at=time.time(),
        )
        return
    try:
        _set_job(job_id, status="running", message="Building solver configuration.")
        omega = float(request.get("solver", {}).get("omega", 1.2))
        if omega <= 0.0 or omega >= 2.0:
            raise ValueError("Legacy SOR omega must be in the open interval (0, 2).")
        source_config = request["config"]
        _validate_render_free_limits(source_config)
        config = _build_config(source_config, omega)
        manifest_path = _create_run_manifest(
            job_id, request, source_config, config, omega, mode="async"
        )
        _set_job(job_id, manifest_path=str(manifest_path))
        _set_job(job_id, message="Solving sparse thermal system.")
        solve_started_at = time.perf_counter()
        solve_started_iso = _utc_now_iso()
        result = solve_steady_state(config)
        solve_finished_at = time.perf_counter()
        solve_finished_iso = _utc_now_iso()
        _set_job(job_id, message="Preparing temperature views.")
        response = _payload_from_result(result, source_config)
        response_prepared_iso = _utc_now_iso()
        _update_run_manifest(
            job_id,
            status="done",
            finished_at=response_prepared_iso,
            timing={
                "solver_started_at": solve_started_iso,
                "solver_finished_at": solve_finished_iso,
                "solver_wall_time_s": solve_finished_at - solve_started_at,
                "response_prepared_at": response_prepared_iso,
                "total_wall_time_s": solve_finished_at - solve_started_at,
            },
            result=response,
            response_payload=response,
            error=None,
        )
        _set_job(
            job_id,
            status="done",
            message="Solver complete.",
            result=response,
            finished_at=time.time(),
        )
    except Exception as exc:
        _update_run_manifest(
            job_id,
            status="error",
            finished_at=_utc_now_iso(),
            error=str(exc),
        )
        _set_job(
            job_id,
            status="error",
            message="Solver failed.",
            error=str(exc),
            finished_at=time.time(),
        )
    finally:
        _release_solver_slot()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def copyfile(self, source, outputfile) -> None:
        try:
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/simulate/status":
            super().do_GET()
            return
        query = parse_qs(parsed.query)
        job_id = query.get("job_id", [""])[0]
        snapshot = _job_snapshot(job_id)
        status = 404 if snapshot.get("status") == "missing" else 200
        self._send_json(snapshot, status)

    def do_POST(self) -> None:
        if self.path not in {"/api/simulate", "/api/simulate/start", "/api/components/import"}:
            self.send_error(404, "Unknown endpoint")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/api/components/import":
                self._send_json(_normalize_component_array(request))
                return

            if self.path == "/api/simulate/start":
                job_id = uuid.uuid4().hex
                with JOBS_LOCK:
                    JOBS[job_id] = {
                        "status": "queued",
                        "message": "Solver job queued.",
                        "created_at": time.time(),
                    }
                worker = threading.Thread(
                    target=_run_solver_job,
                    args=(job_id, request),
                    daemon=True,
                )
                worker.start()
                self._send_json({"job_id": job_id, "status": "queued"}, 202)
                return

            omega = float(request.get("solver", {}).get("omega", 1.2))
            if omega <= 0.0 or omega >= 2.0:
                raise ValueError("Legacy SOR omega must be in the open interval (0, 2).")
            source_config = request["config"]
            _validate_render_free_limits(source_config)
            if not _try_acquire_solver_slot():
                raise ValueError(
                    "Render Free demo allows only one solver job at a time. Try again after the current run finishes."
                )
            try:
                config = _build_config(source_config, omega)
                job_id = uuid.uuid4().hex
                manifest_path = _create_run_manifest(
                    job_id, request, source_config, config, omega, mode="sync"
                )
                solve_started_at = time.perf_counter()
                solve_started_iso = _utc_now_iso()
                result = solve_steady_state(config)
                solve_finished_at = time.perf_counter()
                solve_finished_iso = _utc_now_iso()
                response = _payload_from_result(result, source_config)
                response_prepared_iso = _utc_now_iso()
                _update_run_manifest(
                    job_id,
                    status="done",
                    finished_at=response_prepared_iso,
                    timing={
                        "solver_started_at": solve_started_iso,
                        "solver_finished_at": solve_finished_iso,
                        "solver_wall_time_s": solve_finished_at - solve_started_at,
                        "response_prepared_at": response_prepared_iso,
                        "total_wall_time_s": solve_finished_at - solve_started_at,
                    },
                    result=response,
                    response_payload=response,
                    error=None,
                )
                response["job_id"] = job_id
                response["manifest_path"] = str(manifest_path)
                self._send_json(response)
            finally:
                _release_solver_slot()
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Render Free optimized PCB temperature app.")
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host to bind. Default: 0.0.0.0, or HOST from the environment.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "1085")),
        help="Port to bind. Default: 1085, or PORT from the environment.",
    )
    args = parser.parse_args()

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        if exc.errno == 48:
            raise SystemExit(
                f"Port {args.port} is already in use on {args.host}.\n"
                f"If that is your running Version4 server, open "
                f"http://127.0.0.1:{args.port}/pcb_temperature_app.html instead.\n"
                f"Otherwise stop the other process or run: python3 server.py --port {args.port + 1}"
            ) from exc
        raise

    print(f"Serving Render optimized Version4 at http://{args.host}:{args.port}/pcb_temperature_app.html")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
