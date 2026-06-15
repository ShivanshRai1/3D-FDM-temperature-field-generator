from __future__ import annotations

import argparse
from pathlib import Path

from .io import load_config, save_npz, save_summary
from .solver import solve_steady_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a 3D steady-state PCB temperature field."
    )
    parser.add_argument("config", type=Path, help="JSON simulation config.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/temperature_field.npz"),
        help="Compressed NPZ output containing the 3D field.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("outputs/summary.json"),
        help="JSON output with convergence and component temperatures.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_config(args.config)
    result = solve_steady_state(config)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    save_npz(result, args.out)
    save_summary(result, args.summary)

    summary = result.summary()
    print(f"Converged: {summary['converged']} after {summary['iterations']} iterations")
    print(f"Grid shape: {summary['grid_shape']}")
    print(f"Maximum board temperature: {summary['max_temperature_k']:.3f} K")
    for report in summary["component_reports"]:
        print(
            f"{report['name']}: board max {report['board_max_temperature_k']:.3f} K, "
            f"estimated junction {report['estimated_junction_temperature_k']:.3f} K"
        )


if __name__ == "__main__":
    main()
