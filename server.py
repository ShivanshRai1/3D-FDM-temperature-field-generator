from __future__ import annotations

import argparse
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
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def _float(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    return float(value)


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
        radiation_outer_iterations=int(payload.get("radiation_outer_iterations", 1)),
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
    return {
        "generated_at": "backend",
        "solver": {
            "iterations": int(result.iterations),
            "converged": bool(result.converged),
            "max_delta_k": float(result.max_delta_k),
            "diagnostics": summary.get("diagnostics", {}),
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


def _run_solver_job(job_id: str, request: dict[str, Any]) -> None:
    try:
        _set_job(job_id, status="running", message="Building solver configuration.")
        omega = float(request.get("solver", {}).get("omega", 1.2))
        if omega <= 0.0 or omega >= 2.0:
            raise ValueError("Legacy SOR omega must be in the open interval (0, 2).")
        source_config = request["config"]
        config = _build_config(source_config, omega)
        _set_job(job_id, message="Solving sparse thermal system.")
        result = solve_steady_state(config)
        _set_job(job_id, message="Preparing temperature views.")
        response = _payload_from_result(result, source_config)
        _set_job(
            job_id,
            status="done",
            message="Solver complete.",
            result=response,
            finished_at=time.time(),
        )
    except Exception as exc:
        _set_job(
            job_id,
            status="error",
            message="Solver failed.",
            error=str(exc),
            finished_at=time.time(),
        )


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
        if self.path not in {"/api/simulate", "/api/simulate/start"}:
            self.send_error(404, "Unknown endpoint")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
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
            config = _build_config(source_config, omega)
            result = solve_steady_state(config)
            response = _payload_from_result(result, source_config)
            self._send_json(response)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Version3 PCB temperature app.")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "9023")),
        help="Port to bind on 127.0.0.1. Default: 9023, or PORT from the environment.",
    )
    args = parser.parse_args()

    try:
        server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    except OSError as exc:
        if exc.errno == 48:
            raise SystemExit(
                f"Port {args.port} is already in use on 127.0.0.1.\n"
                f"If that is your running Version3 server, open "
                f"http://127.0.0.1:{args.port}/pcb_temperature_app.html instead.\n"
                f"Otherwise stop the other process or run: python3 server.py --port {args.port + 1}"
            ) from exc
        raise

    print(f"Serving Version3 at http://0.0.0.0:{args.port}/pcb_temperature_app.html")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
