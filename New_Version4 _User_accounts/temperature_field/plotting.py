from __future__ import annotations

from pathlib import Path

import numpy as np


def save_midplane_csv(npz_path: str | Path, csv_path: str | Path, z_index: int | None = None) -> None:
    """Export one XY temperature slice from a saved NPZ result."""

    data = np.load(npz_path)
    temperature = data["temperature_k"]
    if z_index is None:
        z_index = temperature.shape[2] - 1
    np.savetxt(csv_path, temperature[:, :, z_index], delimiter=",", fmt="%.6f")
