from __future__ import annotations

import unittest

import numpy as np

from temperature_field import (
    Board,
    BoundaryCondition,
    Component,
    Layer,
    SimulationConfig,
    SolverSettings,
    component_equivalent_conductivity_w_mk,
    solve_steady_state,
)
from temperature_field.thermal_resistance import estimate_steady_state_resistance


class SolverTests(unittest.TestCase):
    def test_no_heat_converges_to_ambient(self) -> None:
        config = SimulationConfig(
            board=Board(10.0, 8.0, 1.0, 2.0, 2.0, 0.5),
            boundary=BoundaryCondition(ambient_temperature_k=310.0, surrounding_temperature_k=310.0),
            solver=SolverSettings(initial_temperature_k=300.0, tolerance_k=1e-7),
            layers=[Layer("FR4", 0.0, 1.0, 0.35)],
            components=[],
        )
        result = solve_steady_state(config)
        self.assertTrue(result.converged)
        self.assertLess(abs(float(np.max(result.temperature_k)) - 310.0), 1e-4)

    def test_component_heat_raises_temperature(self) -> None:
        config = SimulationConfig(
            board=Board(20.0, 20.0, 1.0, 2.0, 2.0, 0.5),
            solver=SolverSettings(initial_temperature_k=300.0, tolerance_k=1e-5),
            layers=[Layer("FR4", 0.0, 1.0, 0.35)],
            components=[
                Component(
                    name="U1",
                    x_mm=8.0,
                    y_mm=8.0,
                    width_mm=4.0,
                    depth_mm=4.0,
                    height_mm=1.0,
                    power_w=1.0,
                    steady_state_thermal_resistance_k_per_w=20.0,
                )
            ],
        )
        result = solve_steady_state(config)
        self.assertTrue(result.converged)
        self.assertGreater(float(np.max(result.temperature_k)), 300.0)
        report = result.component_reports[0]
        self.assertAlmostEqual(report.equivalent_thermal_conductivity_w_mk, 3.125)
        self.assertAlmostEqual(report.junction_rise_k, 20.0)
        self.assertAlmostEqual(
            report.estimated_junction_temperature_k,
            config.boundary.ambient_temperature_k + report.junction_rise_k,
        )
        self.assertAlmostEqual(float(np.sum(result.heat_w)), 1.0)

    def test_junction_to_case_requires_case_to_ambient_path_for_report(self) -> None:
        config = SimulationConfig(
            board=Board(20.0, 20.0, 1.0, 2.0, 2.0, 0.5),
            boundary=BoundaryCondition(ambient_temperature_k=305.0, surrounding_temperature_k=305.0),
            solver=SolverSettings(initial_temperature_k=305.0, tolerance_k=1e-5),
            layers=[Layer("FR4", 0.0, 1.0, 0.35)],
            components=[
                Component(
                    name="Q1",
                    x_mm=8.0,
                    y_mm=8.0,
                    width_mm=4.0,
                    depth_mm=4.0,
                    height_mm=1.0,
                    power_w=2.0,
                    steady_state_thermal_resistance_k_per_w=4.0,
                    thermal_resistance_mode="junction_to_case",
                    case_to_ambient_thermal_resistance_k_per_w=11.0,
                )
            ],
        )
        report = solve_steady_state(config).component_reports[0]
        self.assertEqual(report.thermal_resistance_mode, "junction_to_case")
        self.assertAlmostEqual(report.junction_rise_k, 30.0)
        self.assertAlmostEqual(report.estimated_junction_temperature_k, 335.0)

    def test_thin_copper_layer_is_exact_z_slab(self) -> None:
        config = SimulationConfig(
            board=Board(10.0, 10.0, 1.6, 2.0, 2.0, 0.2),
            solver=SolverSettings(initial_temperature_k=300.0, tolerance_k=1e-5),
            layers=[
                Layer("FR4", 0.0, 1.6, 0.35),
                Layer("Top copper", 1.565, 1.6, 385.0),
            ],
            components=[],
        )
        result = solve_steady_state(config)
        z_edges_mm = result.z_edges_m * 1000.0
        self.assertTrue(np.any(np.isclose(z_edges_mm, 1.565)))
        self.assertTrue(np.any(np.isclose(z_edges_mm, 1.6)))
        copper_cells = np.where(np.isclose(result.conductivity_w_mk[0, 0, :], 385.0))[0]
        self.assertEqual(len(copper_cells), 1)
        copper_index = int(copper_cells[0])
        copper_thickness_mm = (result.z_edges_m[copper_index + 1] - result.z_edges_m[copper_index]) * 1000.0
        self.assertAlmostEqual(copper_thickness_mm, 0.035)

    def test_component_smaller_than_grid_still_injects_power_by_overlap(self) -> None:
        config = SimulationConfig(
            board=Board(20.0, 20.0, 1.0, 5.0, 5.0, 0.5),
            solver=SolverSettings(initial_temperature_k=300.0, tolerance_k=1e-5),
            layers=[Layer("FR4", 0.0, 1.0, 0.35)],
            components=[
                Component(
                    name="Tiny",
                    x_mm=2.2,
                    y_mm=2.2,
                    width_mm=0.4,
                    depth_mm=0.4,
                    height_mm=0.5,
                    power_w=0.25,
                    steady_state_thermal_resistance_k_per_w=10.0,
                )
            ],
        )
        result = solve_steady_state(config)
        self.assertAlmostEqual(float(np.sum(result.heat_w)), 0.25)
        self.assertEqual(result.component_reports[0].occupied_cell_count, 1)

    def test_component_rth_does_not_overwrite_board_conductivity(self) -> None:
        config = SimulationConfig(
            board=Board(10.0, 10.0, 1.0, 2.0, 2.0, 0.5),
            solver=SolverSettings(initial_temperature_k=300.0, tolerance_k=1e-5),
            layers=[Layer("FR4", 0.0, 1.0, 0.35)],
            components=[
                Component(
                    name="U1",
                    x_mm=2.0,
                    y_mm=2.0,
                    width_mm=4.0,
                    depth_mm=4.0,
                    height_mm=1.0,
                    power_w=1.0,
                    steady_state_thermal_resistance_k_per_w=20.0,
                )
            ],
        )
        result = solve_steady_state(config)
        self.assertTrue(np.allclose(result.conductivity_w_mk, 0.35))

    def test_ambient_shift_is_not_double_counted(self) -> None:
        base = SimulationConfig(
            board=Board(10.0, 10.0, 1.0, 2.0, 2.0, 0.5),
            boundary=BoundaryCondition(ambient_temperature_k=300.0, surrounding_temperature_k=300.0),
            solver=SolverSettings(initial_temperature_k=300.0, tolerance_k=1e-7),
            layers=[Layer("FR4", 0.0, 1.0, 0.35)],
            components=[],
        )
        warmer = SimulationConfig(
            board=base.board,
            boundary=BoundaryCondition(ambient_temperature_k=315.0, surrounding_temperature_k=315.0),
            solver=SolverSettings(initial_temperature_k=315.0, tolerance_k=1e-7),
            layers=base.layers,
            components=[],
        )
        base_result = solve_steady_state(base)
        warmer_result = solve_steady_state(warmer)
        self.assertAlmostEqual(
            float(np.mean(warmer_result.temperature_k - base_result.temperature_k)),
            15.0,
            places=5,
        )

    def test_rth_to_conductivity_formula_uses_height_over_rth_area(self) -> None:
        component = Component(
            name="U2",
            x_mm=0.0,
            y_mm=0.0,
            width_mm=10.0,
            depth_mm=5.0,
            height_mm=2.0,
            power_w=1.0,
            steady_state_thermal_resistance_k_per_w=20.0,
        )
        self.assertAlmostEqual(component_equivalent_conductivity_w_mk(component), 2.0)

    def test_estimate_steady_state_resistance_from_plateau(self) -> None:
        times = [0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]
        zth = [1.0, 4.0, 8.0, 9.8, 10.0, 10.02]
        self.assertAlmostEqual(
            estimate_steady_state_resistance(times, zth, tail_fraction=0.5),
            (9.8 + 10.0 + 10.02) / 3.0,
        )


if __name__ == "__main__":
    unittest.main()
