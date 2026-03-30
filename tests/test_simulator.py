from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ev_pq_demo.scenarios import get_preset
from ev_pq_demo.simulator import ChargingSession, SiteConfig, run_simulation


class SimulatorTests(unittest.TestCase):
    def test_office_scenario_generates_only_ac_sessions(self) -> None:
        preset = get_preset("office_commute")
        sessions = preset.generator(seed=7, duration_hours=24)

        self.assertEqual(len(sessions), 26)
        self.assertTrue(all(session.required_mode == "ac" for session in sessions))
        self.assertTrue(all(session.departure_minute > session.arrival_minute for session in sessions))

    def test_grid_aware_limits_peak_below_reserved_threshold(self) -> None:
        sessions = [
            ChargingSession("S1", 0, 240, 55.0, 30.0, "ac", 22.0, 3, "Van 1"),
            ChargingSession("S2", 0, 240, 55.0, 25.0, "ac", 22.0, 3, "Van 2"),
            ChargingSession("S3", 0, 240, 55.0, 28.0, "ac", 22.0, 3, "Van 3"),
            ChargingSession("S4", 0, 240, 55.0, 20.0, "ac", 22.0, 3, "Van 4"),
        ]
        site = SiteConfig(
            transformer_limit_kw=70.0,
            feeder_limit_kw=70.0,
            base_load_kw=10.0,
            ac_connectors=4,
            ac_power_kw=22.0,
            ac_phases=3,
            dc_connectors=0,
            dc_power_kw=0.0,
            reserve_pct=20.0,
            background_thd_pct=1.5,
        )

        uncontrolled = run_simulation(
            sessions,
            site,
            "uncontrolled",
            step_minutes=15,
            duration_hours=4,
            label="Uncontrolled test",
        )
        grid_aware = run_simulation(
            sessions,
            site,
            "grid_aware",
            step_minutes=15,
            duration_hours=4,
            label="Grid aware test",
        )

        self.assertGreater(uncontrolled["summary"]["peak_site_kw"], grid_aware["summary"]["peak_site_kw"])
        self.assertLessEqual(grid_aware["summary"]["peak_site_kw"], 56.1)

    def test_public_hub_run_returns_timeline_and_summary(self) -> None:
        preset = get_preset("public_fast_hub")
        sessions = preset.generator(seed=5, duration_hours=24)
        result = run_simulation(
            sessions,
            SiteConfig(**preset.recommended_site),
            preset.default_policy,
            step_minutes=preset.default_step_minutes,
            duration_hours=preset.default_duration_hours,
            label="Hub smoke test",
        )

        self.assertGreater(len(result["timeline"]), 0)
        self.assertIn("headline", result)
        self.assertGreater(result["summary"]["energy_requested_kwh"], 0.0)


if __name__ == "__main__":
    unittest.main()
