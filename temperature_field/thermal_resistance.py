from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def estimate_steady_state_resistance(
    times_s: Sequence[float],
    transient_impedance_k_per_w: Sequence[float],
    tail_fraction: float = 0.15,
    plateau_slope_limit_per_decade: float = 0.03,
) -> float:
    """Estimate steady-state Rth from the tail of a transient thermal impedance curve.

    Datasheet Zth curves usually approach the steady-state thermal resistance at
    long pulse times. This helper averages the final part of the curve and checks
    that it is close to a plateau on a log-time axis.
    """

    times = np.asarray(times_s, dtype=float)
    zth = np.asarray(transient_impedance_k_per_w, dtype=float)
    if times.shape != zth.shape or times.ndim != 1:
        raise ValueError("times_s and transient_impedance_k_per_w must be equal-length 1D arrays.")
    if len(times) < 3:
        raise ValueError("At least three curve points are required.")
    if np.any(times <= 0.0) or np.any(zth <= 0.0):
        raise ValueError("Curve points must be positive.")

    order = np.argsort(times)
    times = times[order]
    zth = zth[order]

    tail_count = max(3, int(np.ceil(len(times) * tail_fraction)))
    tail_count = min(tail_count, len(times))
    tail_times = times[-tail_count:]
    tail_zth = zth[-tail_count:]

    log_time = np.log10(tail_times)
    slope, _ = np.polyfit(log_time, tail_zth, deg=1)
    estimate = float(np.mean(tail_zth))
    relative_slope = abs(float(slope)) / estimate
    if relative_slope > plateau_slope_limit_per_decade:
        raise ValueError(
            "Transient impedance tail has not reached a clear steady-state plateau. "
            f"Relative slope is {relative_slope:.4f} per decade; limit is "
            f"{plateau_slope_limit_per_decade:.4f}."
        )
    return estimate
