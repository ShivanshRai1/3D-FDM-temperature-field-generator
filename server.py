from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import asdict
from datetime import datetime, timezone
import json
import multiprocessing as mp
import os
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

# Force single-thread BLAS by default before NumPy/SciPy initialize.
# This protects deployments where dashboard/render.yaml env vars are missing.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

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
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
MAX_CELLS = int(os.environ.get("SOLVER_MAX_CELLS", "250000"))
MAX_RADIATION_OUTER = int(os.environ.get("SOLVER_MAX_RADIATION_OUTER", "4"))
SOLVER_TIMEOUT_S = int(os.environ.get("SOLVER_TIMEOUT_S", "0"))  # 0 = no limit
MIN_DX_MM = float(os.environ.get("SOLVER_MIN_DX_MM", "0"))
MIN_DY_MM = float(os.environ.get("SOLVER_MIN_DY_MM", "0"))
MIN_DZ_MM = float(os.environ.get("SOLVER_MIN_DZ_MM", "0"))
MIN_TOLERANCE_K = float(os.environ.get("SOLVER_MIN_TOLERANCE_K", "0"))
MAX_LINEAR_ITERATIONS = int(os.environ.get("SOLVER_MAX_LINEAR_ITERATIONS", "20000"))
MANIFEST_SYNC_MODE = os.environ.get("MANIFEST_SYNC_MODE", "none").strip().lower()
MANIFEST_GITHUB_REPO = os.environ.get("MANIFEST_GITHUB_REPO", "").strip()
MANIFEST_GITHUB_BRANCH = os.environ.get("MANIFEST_GITHUB_BRANCH", "main").strip() or "main"
MANIFEST_GITHUB_PATH = (
    os.environ.get("MANIFEST_GITHUB_PATH", "temp/simulation_runs").strip().strip("/")
)
MANIFEST_GITHUB_TOKEN = os.environ.get("MANIFEST_GITHUB_TOKEN", "").strip()


def _solver_subprocess_entry(config: SimulationConfig, conn: Any) -> None:
    """Run the solver in a child process so OOM kills the worker, not the HTTP server."""
    try:
        result = solve_steady_state(config)
        conn.send(("ok", result))
    except Exception as exc:
        conn.send(("error", exc))
    finally:
        conn.close()


def _read_subprocess_solver_result(
    proc: mp.Process, parent_conn: Any, timeout_s: int
) -> Any:
    timed_out = False
    if timeout_s > 0:
        if not parent_conn.poll(timeout_s):
            timed_out = True
            proc.terminate()
            proc.join(timeout=5)
    else:
        proc.join()

    if timed_out:
        raise ValueError(
            f"Solver exceeded the {timeout_s}s time limit. "
            f"Try a coarser grid (increase dx/dy/dz)."
        )

    if parent_conn.poll():
        status, payload = parent_conn.recv()
        if status == "ok":
            return payload
        if isinstance(payload, Exception):
            raise payload
        raise RuntimeError(str(payload))

    if proc.exitcode not in (0, None):
        if proc.exitcode == -9:
            raise ValueError(
                "Solver process was killed, usually from out-of-memory pressure. "
                "Try coarser dx/dy/dz, fewer radiation iterations, or a larger server."
            )
        raise RuntimeError(
            f"Solver process exited with code {proc.exitcode} without returning a result."
        )

    raise RuntimeError("Solver process ended without returning a result.")


def _solve_in_subprocess(config: SimulationConfig) -> Any:
    """Isolate async browser jobs from the HTTP server process."""
    ctx = mp.get_context("spawn" if os.name == "nt" else "fork")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_solver_subprocess_entry, args=(config, child_conn))
    proc.start()
    child_conn.close()
    try:
        return _read_subprocess_solver_result(proc, parent_conn, SOLVER_TIMEOUT_S)
    finally:
        parent_conn.close()
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)


def _solve_with_hard_timeout(config: SimulationConfig) -> Any:
    if SOLVER_TIMEOUT_S <= 0:
        return solve_steady_state(config)
    # Use a thread (not subprocess) to avoid spawn overhead on single-CPU containers.
    # We do NOT use 'with' executor because shutdown(wait=True) would block past timeout.
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(solve_steady_state, config)
    try:
        result = future.result(timeout=SOLVER_TIMEOUT_S)
        executor.shutdown(wait=False)
        return result
    except FuturesTimeoutError:
        executor.shutdown(wait=False)
        raise ValueError(
            f"Solver exceeded the {SOLVER_TIMEOUT_S}s time limit. "
            f"Try a coarser grid (increase dx/dy/dz)."
        )


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
    dx_mm = max(dx_mm, MIN_DX_MM) if MIN_DX_MM > 0.0 else dx_mm
    dy_mm = max(dy_mm, MIN_DY_MM) if MIN_DY_MM > 0.0 else dy_mm
    dz_mm = max(dz_mm, MIN_DZ_MM) if MIN_DZ_MM > 0.0 else dz_mm

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

    # Cap radiation outer iterations to keep solves responsive on the deployed tier.
    radiation_outer = min(
        MAX_RADIATION_OUTER,
        max(1, int(payload.get("radiation_outer_iterations", 1))),
    )

    solver = SolverSettings(
        initial_temperature_k=boundary.ambient_temperature_k,
        relaxation_factor=omega,
        tolerance_k=max(float(payload.get("solver_tolerance_k", 1e-4)), MIN_TOLERANCE_K),
        max_iterations=min(int(payload.get("solver_max_iterations", 20_000)), MAX_LINEAR_ITERATIONS),
        radiation_outer_iterations=radiation_outer,
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


def _estimate_cell_count(config: SimulationConfig) -> int:
    import math
    board = config.board
    nx = max(1, math.ceil(board.length_mm / board.dx_mm))
    ny = max(1, math.ceil(board.width_mm / board.dy_mm))
    # rough z-cell estimate: thickness / dz, plus extra planes for copper layers
    nz = max(1, math.ceil(board.thickness_mm / board.dz_mm)) + 4 * len(config.layers)
    return nx * ny * nz


def _check_grid_size(config: SimulationConfig) -> None:
    estimated = _estimate_cell_count(config)
    if estimated > MAX_CELLS:
        board = config.board
        raise ValueError(
            f"Grid too large for this server: estimated {estimated:,} cells "
            f"(limit {MAX_CELLS:,}). "
            f"Please increase dx/dy/dz. "
            f"Current: dx={board.dx_mm}mm, dy={board.dy_mm}mm, dz={board.dz_mm}mm. "
            f"Try dx=dy=1.0mm and dz=0.2mm to stay within limits."
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest_path(job_id: str) -> Path:
    return RUN_MANIFEST_DIR / f"{job_id}.json"


def _manifest_repo_path(job_id: str) -> str:
    base = MANIFEST_GITHUB_PATH or "temp/simulation_runs"
    return f"{base}/{job_id}.json"


def _github_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {MANIFEST_GITHUB_TOKEN}",
        "User-Agent": "pcb-temperature-app-manifest-sync",
    }


def _github_get_file_sha(path: str) -> str | None:
    encoded_path = quote(path, safe="/")
    url = (
        f"https://api.github.com/repos/{MANIFEST_GITHUB_REPO}/contents/{encoded_path}"
        f"?ref={quote(MANIFEST_GITHUB_BRANCH)}"
    )
    request = Request(url, headers=_github_headers(), method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            sha = payload.get("sha")
            return str(sha) if sha else None
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _sync_manifest_to_github(job_id: str, payload: dict[str, Any]) -> None:
    if MANIFEST_SYNC_MODE != "github":
        return
    if not (MANIFEST_GITHUB_REPO and MANIFEST_GITHUB_TOKEN):
        return

    try:
        repo_path = _manifest_repo_path(job_id)
        current_sha = _github_get_file_sha(repo_path)
        content = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        encoded_content = base64.b64encode(content).decode("ascii")
        body: dict[str, Any] = {
            "message": f"Auto: update simulation manifest {job_id}",
            "content": encoded_content,
            "branch": MANIFEST_GITHUB_BRANCH,
        }
        if current_sha:
            body["sha"] = current_sha

        encoded_path = quote(repo_path, safe="/")
        url = f"https://api.github.com/repos/{MANIFEST_GITHUB_REPO}/contents/{encoded_path}"
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={**_github_headers(), "Content-Type": "application/json"},
            method="PUT",
        )
        with urlopen(request, timeout=30):
            return
    except Exception as exc:
        print(f"Manifest sync failed for {job_id}: {exc}")


def _write_run_manifest(job_id: str, payload: dict[str, Any]) -> Path:
    RUN_MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = _manifest_path(job_id)
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    temp_path.replace(path)
    if MANIFEST_SYNC_MODE == "github":
        worker = threading.Thread(
            target=_sync_manifest_to_github,
            args=(job_id, payload),
            daemon=True,
        )
        worker.start()
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
        "timing": {
            "solver_started_at": None,
            "solver_finished_at": None,
            "solver_wall_time_s": None,
            "response_prepared_at": None,
            "total_wall_time_s": None,
        },
        "result_summary": None,
        "error": None,
    }
    return _write_run_manifest(job_id, manifest)


def _manifest_result_summary(response: dict[str, Any]) -> dict[str, Any]:
    solver = response.get("solver", {})
    component_reports = response.get("component_reports", [])
    views = response.get("views", {})
    views_meta: dict[str, dict[str, Any]] = {}
    for name, view in views.items():
        if not isinstance(view, dict):
            continue
        views_meta[name] = {
            "name": view.get("name"),
            "z": view.get("z"),
            "nx": view.get("nx"),
            "ny": view.get("ny"),
        }
    return {
        "solver": solver,
        "min_temperature_k": response.get("min_temperature_k"),
        "max_temperature_k": response.get("max_temperature_k"),
        "component_reports": component_reports,
        "views_meta": views_meta,
    }


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
        if len(row) >= 7:
            rth_value = row[5]
            name_value = row[6]
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
                "power": max(0.0, default_power_w),
                "rth": rth,
                "rotation": 0,
                "rthMissing": rth_missing,
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


def _has_active_job() -> bool:
    with JOBS_LOCK:
        for job in JOBS.values():
            status = str(job.get("status", "")).lower()
            if status in {"queued", "running"}:
                return True
    return False


def _run_solver_job(job_id: str, request: dict[str, Any]) -> None:
    try:
        _set_job(job_id, status="running", message="Building solver configuration.")
        omega = float(request.get("solver", {}).get("omega", 1.2))
        if omega <= 0.0 or omega >= 2.0:
            raise ValueError("Legacy SOR omega must be in the open interval (0, 2).")
        source_config = request["config"]
        config = _build_config(source_config, omega)
        _check_grid_size(config)
        manifest_path = _create_run_manifest(
            job_id, request, source_config, config, omega, mode="async"
        )
        _set_job(job_id, manifest_path=str(manifest_path))
        _set_job(job_id, message="Solving sparse thermal system.")
        solve_started_at = time.perf_counter()
        solve_started_iso = _utc_now_iso()
        result = _solve_in_subprocess(config)
        solve_finished_at = time.perf_counter()
        solve_finished_iso = _utc_now_iso()
        _set_job(job_id, message="Preparing temperature views.")
        response = _payload_from_result(result, source_config)
        response_prepared_iso = _utc_now_iso()
        _set_job(
            job_id,
            status="done",
            message="Solver complete.",
            result=response,
            finished_at=time.time(),
        )
        manifest_worker = threading.Thread(
            target=_update_run_manifest,
            kwargs={
                "job_id": job_id,
                "status": "done",
                "finished_at": response_prepared_iso,
                "timing": {
                    "solver_started_at": solve_started_iso,
                    "solver_finished_at": solve_finished_iso,
                    "solver_wall_time_s": solve_finished_at - solve_started_at,
                    "response_prepared_at": response_prepared_iso,
                    "total_wall_time_s": solve_finished_at - solve_started_at,
                },
                "result_summary": _manifest_result_summary(response),
                "error": None,
            },
            daemon=True,
        )
        manifest_worker.start()
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


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def _send_no_body(self, status: int = 200, extra_headers: dict[str, str] | None = None) -> None:
        try:
            self.send_response(status)
            if extra_headers:
                for key, value in extra_headers.items():
                    self.send_header(key, value)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

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

        if parsed.path in {"/healthz", "/api/health"}:
            self._send_json({"status": "ok"})
            return

        # Redirect root to the app
        if parsed.path == "/":
            self.send_response(302)
            self.send_header("Location", "/pcb_temperature_app.html")
            self.end_headers()
            return

        # Handle API status endpoint
        if parsed.path == "/api/simulate/status":
            query = parse_qs(parsed.query)
            job_id = query.get("job_id", [""])[0]
            snapshot = _job_snapshot(job_id)
            status = 404 if snapshot.get("status") == "missing" else 200
            self._send_json(snapshot, status)
            return

        # Serve static files
        super().do_GET()

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path in {"/healthz", "/api/health"}:
            self._send_no_body(200)
            return

        if parsed.path == "/":
            self._send_no_body(302, {"Location": "/pcb_temperature_app.html"})
            return

        if parsed.path == "/api/simulate/status":
            query = parse_qs(parsed.query)
            job_id = query.get("job_id", [""])[0]
            snapshot = _job_snapshot(job_id)
            status = 404 if snapshot.get("status") == "missing" else 200
            self._send_no_body(status)
            return

        super().do_HEAD()

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
                if _has_active_job():
                    self._send_json(
                        {
                            "error": (
                                "A simulation is already running on this server. "
                                "Please wait for it to finish before starting another run."
                            )
                        },
                        429,
                    )
                    return
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
            if _has_active_job():
                self._send_json(
                    {
                        "error": (
                            "A simulation is already running on this server. "
                            "Please wait for it to finish before starting another run."
                        )
                    },
                    429,
                )
                return
            source_config = request["config"]
            config = _build_config(source_config, omega)
            _check_grid_size(config)
            job_id = uuid.uuid4().hex
            manifest_path = _create_run_manifest(
                job_id, request, source_config, config, omega, mode="sync"
            )
            solve_started_at = time.perf_counter()
            solve_started_iso = _utc_now_iso()
            result = _solve_with_hard_timeout(config)
            solve_finished_at = time.perf_counter()
            solve_finished_iso = _utc_now_iso()
            response = _payload_from_result(result, source_config)
            response_prepared_iso = _utc_now_iso()
            manifest_worker = threading.Thread(
                target=_update_run_manifest,
                kwargs={
                    "job_id": job_id,
                    "status": "done",
                    "finished_at": response_prepared_iso,
                    "timing": {
                        "solver_started_at": solve_started_iso,
                        "solver_finished_at": solve_finished_iso,
                        "solver_wall_time_s": solve_finished_at - solve_started_at,
                        "response_prepared_at": response_prepared_iso,
                        "total_wall_time_s": solve_finished_at - solve_started_at,
                    },
                    "result_summary": _manifest_result_summary(response),
                    "error": None,
                },
                daemon=True,
            )
            manifest_worker.start()
            response["job_id"] = job_id
            response["manifest_path"] = str(manifest_path)
            self._send_json(response)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Version4 PCB temperature app.")
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
                f"Port {args.port} is already in use on 0.0.0.0.\n"
                f"If that is your running Version4 server, open "
                f"http://127.0.0.1:{args.port}/pcb_temperature_app.html instead.\n"
                f"Otherwise stop the other process or run: python3 server.py --port {args.port + 1}"
            ) from exc
        raise

    print(f"Serving Version4 at http://0.0.0.0:{args.port}/pcb_temperature_app.html")
    print(
        "BLAS thread env: "
        f"OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')} "
        f"OPENBLAS_NUM_THREADS={os.environ.get('OPENBLAS_NUM_THREADS')} "
        f"MKL_NUM_THREADS={os.environ.get('MKL_NUM_THREADS')} "
        f"NUMEXPR_NUM_THREADS={os.environ.get('NUMEXPR_NUM_THREADS')}"
    )
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
