from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Callable

from .simulator import ChargingSession


@dataclass(frozen=True)
class ScenarioPreset:
    key: str
    name: str
    description: str
    plain_language: str
    default_policy: str
    default_duration_hours: int
    default_step_minutes: int
    recommended_site: dict[str, float | int]
    generator: Callable[[int, int], list[ChargingSession]]

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "plain_language": self.plain_language,
            "default_policy": self.default_policy,
            "default_duration_hours": self.default_duration_hours,
            "default_step_minutes": self.default_step_minutes,
            "recommended_site": self.recommended_site,
        }


def _hours_to_minutes(value: float) -> int:
    return max(0, int(round(value * 60)))


def _bounded_hour(rng: random.Random, low: float, high: float) -> float:
    return max(low, min(high, rng.uniform(low, high)))


def generate_office_commute(seed: int, duration_hours: int) -> list[ChargingSession]:
    rng = random.Random(seed)
    duration_minutes = duration_hours * 60
    sessions: list[ChargingSession] = []

    for index in range(26):
        arrival_hour = _bounded_hour(rng, 7.0, 10.5)
        dwell_hours = rng.uniform(6.5, 9.5)
        departure_hour = min(arrival_hour + dwell_hours, duration_hours - 0.25)
        max_power = 7.4 if rng.random() < 0.38 else 11.0
        phases = 1 if max_power < 11.0 and rng.random() < 0.8 else 3
        requested_kwh = rng.uniform(10.0, 28.0)
        initial_soc = rng.uniform(22.0, 68.0)
        vehicle_label = rng.choice(
            ["Commuter hatchback", "Company SUV", "Pool car", "Employee sedan"]
        )

        sessions.append(
            ChargingSession(
                session_id=f"OFF-{index + 1:02d}",
                arrival_minute=min(_hours_to_minutes(arrival_hour), duration_minutes - 15),
                departure_minute=max(
                    min(_hours_to_minutes(departure_hour), duration_minutes),
                    min(_hours_to_minutes(arrival_hour), duration_minutes - 15) + 30,
                ),
                requested_kwh=round(requested_kwh, 1),
                initial_soc_pct=round(initial_soc, 1),
                required_mode="ac",
                max_power_kw=max_power,
                phases=phases,
                vehicle_label=vehicle_label,
            )
        )

    return sorted(sessions, key=lambda item: (item.arrival_minute, item.departure_minute))


def generate_public_fast_hub(seed: int, duration_hours: int) -> list[ChargingSession]:
    rng = random.Random(seed)
    duration_minutes = duration_hours * 60
    sessions: list[ChargingSession] = []

    for index in range(34):
        if rng.random() < 0.55:
            arrival_hour = _bounded_hour(rng, 10.5, 14.5)
        else:
            arrival_hour = _bounded_hour(rng, 16.0, 21.0)

        dwell_hours = rng.uniform(0.35, 1.25)
        departure_hour = min(arrival_hour + dwell_hours, duration_hours - 0.1)
        max_power = rng.choice([60.0, 90.0, 120.0, 150.0])
        requested_kwh = rng.uniform(18.0, 58.0)
        initial_soc = rng.uniform(8.0, 55.0)
        vehicle_label = rng.choice(
            ["Long-range SUV", "Road-trip sedan", "Delivery van", "Taxi EV"]
        )

        sessions.append(
            ChargingSession(
                session_id=f"HUB-{index + 1:02d}",
                arrival_minute=min(_hours_to_minutes(arrival_hour), duration_minutes - 5),
                departure_minute=max(
                    min(_hours_to_minutes(departure_hour), duration_minutes),
                    min(_hours_to_minutes(arrival_hour), duration_minutes - 5) + 15,
                ),
                requested_kwh=round(requested_kwh, 1),
                initial_soc_pct=round(initial_soc, 1),
                required_mode="dc",
                max_power_kw=max_power,
                phases=3,
                vehicle_label=vehicle_label,
            )
        )

    return sorted(sessions, key=lambda item: (item.arrival_minute, item.departure_minute))


PRESETS: dict[str, ScenarioPreset] = {
    "office_commute": ScenarioPreset(
        key="office_commute",
        name="Office Charging",
        description="Most vehicles arrive in the morning, stay for several hours, and use AC charging.",
        plain_language="Good for showing how smart scheduling can smooth out a workplace parking site without making the model too complicated.",
        default_policy="deadline_aware",
        default_duration_hours=24,
        default_step_minutes=15,
        recommended_site={
            "transformer_limit_kw": 250,
            "feeder_limit_kw": 220,
            "base_load_kw": 55,
            "ac_connectors": 16,
            "ac_power_kw": 11,
            "ac_phases": 3,
            "dc_connectors": 1,
            "dc_power_kw": 50,
            "reserve_pct": 12,
            "background_thd_pct": 1.8,
        },
        generator=generate_office_commute,
    ),
    "public_fast_hub": ScenarioPreset(
        key="public_fast_hub",
        name="Public Fast Hub",
        description="Short stays, high charger power, and sharp demand peaks around busy travel times.",
        plain_language="Good for demonstrating overload, voltage dip, and harmonic stress when fast chargers cluster at one site.",
        default_policy="grid_aware",
        default_duration_hours=24,
        default_step_minutes=5,
        recommended_site={
            "transformer_limit_kw": 700,
            "feeder_limit_kw": 650,
            "base_load_kw": 95,
            "ac_connectors": 4,
            "ac_power_kw": 22,
            "ac_phases": 3,
            "dc_connectors": 6,
            "dc_power_kw": 120,
            "reserve_pct": 10,
            "background_thd_pct": 2.2,
        },
        generator=generate_public_fast_hub,
    ),
}


def list_presets() -> list[ScenarioPreset]:
    return list(PRESETS.values())


def get_preset(key: str) -> ScenarioPreset:
    try:
        return PRESETS[key]
    except KeyError as exc:
        raise ValueError(f"Unknown scenario preset: {key}") from exc

