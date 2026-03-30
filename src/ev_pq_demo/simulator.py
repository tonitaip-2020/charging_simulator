from __future__ import annotations

from dataclasses import asdict, dataclass
import math


POLICIES = {
    "uncontrolled": {
        "label": "Uncontrolled",
        "description": "Every connected vehicle charges as fast as it can until the site hits a hard limit.",
    },
    "equal_share": {
        "label": "Equal Share",
        "description": "Available site power is split evenly between connected vehicles.",
    },
    "deadline_aware": {
        "label": "Deadline Aware",
        "description": "Vehicles that need more energy before departure get priority.",
    },
    "grid_aware": {
        "label": "Grid Aware",
        "description": "The controller keeps a safety margin below the site limit, then prioritizes urgent vehicles.",
    },
}

GLOSSARY = [
    {
        "term": "Transformer loading",
        "meaning": "How hard the site transformer is working. Above 100% means the setup is too aggressive.",
    },
    {
        "term": "Voltage",
        "meaning": "A simple estimate of local voltage health. Lower numbers mean the site is being stressed.",
    },
    {
        "term": "Power factor",
        "meaning": "How effectively power is being used. Closer to 1.00 is better.",
    },
    {
        "term": "Phase imbalance",
        "meaning": "How unevenly charging is spread across the three phases. Lower is better.",
    },
    {
        "term": "THD",
        "meaning": "A simple harmonic distortion estimate. Higher values mean a noisier electrical waveform.",
    },
]


@dataclass(frozen=True)
class ChargingSession:
    session_id: str
    arrival_minute: int
    departure_minute: int
    requested_kwh: float
    initial_soc_pct: float
    required_mode: str
    max_power_kw: float
    phases: int
    vehicle_label: str


@dataclass(frozen=True)
class SiteConfig:
    transformer_limit_kw: float
    feeder_limit_kw: float
    base_load_kw: float
    ac_connectors: int
    ac_power_kw: float
    ac_phases: int
    dc_connectors: int
    dc_power_kw: float
    reserve_pct: float = 10.0
    background_thd_pct: float = 1.8


@dataclass
class SessionState:
    spec: ChargingSession
    delivered_kwh: float = 0.0
    queue_minutes: int = 0
    plugged_minutes: int = 0

    @property
    def energy_remaining_kwh(self) -> float:
        return max(self.spec.requested_kwh - self.delivered_kwh, 0.0)


def list_policy_metadata() -> list[dict]:
    return [{"key": key, **value} for key, value in POLICIES.items()]


def build_site_config(raw: dict) -> SiteConfig:
    return SiteConfig(
        transformer_limit_kw=max(float(raw.get("transformer_limit_kw", 250)), 1.0),
        feeder_limit_kw=max(float(raw.get("feeder_limit_kw", 220)), 1.0),
        base_load_kw=max(float(raw.get("base_load_kw", 40)), 0.0),
        ac_connectors=max(int(raw.get("ac_connectors", 10)), 0),
        ac_power_kw=max(float(raw.get("ac_power_kw", 11)), 0.0),
        ac_phases=3 if int(raw.get("ac_phases", 3)) == 3 else 1,
        dc_connectors=max(int(raw.get("dc_connectors", 0)), 0),
        dc_power_kw=max(float(raw.get("dc_power_kw", 50)), 0.0),
        reserve_pct=max(float(raw.get("reserve_pct", 10.0)), 0.0),
        background_thd_pct=max(float(raw.get("background_thd_pct", 1.8)), 0.0),
    )


def run_simulation(
    sessions: list[ChargingSession],
    site: SiteConfig,
    policy_key: str,
    *,
    step_minutes: int,
    duration_hours: int,
    label: str | None = None,
) -> dict:
    if policy_key not in POLICIES:
        raise ValueError(f"Unknown charging policy: {policy_key}")

    step_minutes = max(step_minutes, 1)
    step_hours = step_minutes / 60.0
    horizon_minutes = max(duration_hours * 60, max((item.departure_minute for item in sessions), default=0))
    states = [SessionState(spec=item) for item in sorted(sessions, key=lambda row: (row.arrival_minute, row.departure_minute, row.session_id))]

    timeline: list[dict] = []
    risk_flags = {
        "overload_steps": 0,
        "low_voltage_steps": 0,
        "low_pf_steps": 0,
        "high_imbalance_steps": 0,
        "high_thd_steps": 0,
    }
    previous_site_kw = site.base_load_kw
    peak_queue = 0

    for minute in range(0, horizon_minutes, step_minutes):
        active_states = [
            state
            for state in states
            if state.spec.arrival_minute <= minute < state.spec.departure_minute
            and state.energy_remaining_kwh > 0.05
        ]
        ac_waiting = [state for state in active_states if state.spec.required_mode == "ac"]
        dc_waiting = [state for state in active_states if state.spec.required_mode == "dc"]
        connected = _pick_connected(ac_waiting, site.ac_connectors) + _pick_connected(
            dc_waiting, site.dc_connectors
        )
        queued = [state for state in active_states if state not in connected]

        for state in queued:
            state.queue_minutes += step_minutes
        for state in connected:
            state.plugged_minutes += step_minutes

        peak_queue = max(peak_queue, len(queued))

        session_caps: dict[str, float] = {}
        connected_lookup = {state.spec.session_id: state for state in connected}
        for state in connected:
            pool_power = site.ac_power_kw if state.spec.required_mode == "ac" else site.dc_power_kw
            power_cap = min(
                pool_power,
                state.spec.max_power_kw,
                state.energy_remaining_kwh / step_hours if step_hours else 0.0,
            )
            if power_cap > 1e-6:
                session_caps[state.spec.session_id] = power_cap

        hard_site_limit_kw = max(min(site.transformer_limit_kw, site.feeder_limit_kw) - site.base_load_kw, 0.0)
        effective_site_limit_kw = hard_site_limit_kw

        if policy_key == "grid_aware":
            reserved_total_kw = min(site.transformer_limit_kw, site.feeder_limit_kw) * (
                1.0 - site.reserve_pct / 100.0
            )
            effective_site_limit_kw = min(
                hard_site_limit_kw,
                max(reserved_total_kw - site.base_load_kw, 0.0),
            )

        charging_capacity_kw = min(sum(session_caps.values()), effective_site_limit_kw)
        allocations = _allocate_power(
            policy_key,
            minute,
            step_hours,
            connected_lookup,
            session_caps,
            charging_capacity_kw,
        )

        phase_loads = [site.base_load_kw / 3.0] * 3
        kvar_total = _reactive_power(site.base_load_kw, 0.97)
        harmonic_source = 0.0
        single_phase_index = 0

        for session_id, power_kw in allocations.items():
            if power_kw <= 0.0:
                continue

            state = connected_lookup[session_id]
            delivered_kwh = min(state.energy_remaining_kwh, power_kw * step_hours)
            state.delivered_kwh += delivered_kwh

            session_pf = _power_factor_for_session(state.spec, site)
            kvar_total += _reactive_power(power_kw, session_pf)
            harmonic_source += power_kw * _harmonic_emission_for_session(state.spec, site)

            if state.spec.phases == 1:
                phase_loads[single_phase_index % 3] += power_kw
                single_phase_index += 1
            else:
                split = power_kw / 3.0
                phase_loads = [value + split for value in phase_loads]

        charging_kw = sum(allocations.values())
        total_site_kw = site.base_load_kw + charging_kw
        transformer_loading_pct = _safe_pct(total_site_kw, site.transformer_limit_kw)
        feeder_loading_pct = _safe_pct(total_site_kw, site.feeder_limit_kw)
        load_ratio = total_site_kw / max(min(site.transformer_limit_kw, site.feeder_limit_kw), 1.0)

        avg_phase_kw = sum(phase_loads) / 3.0 if phase_loads else 0.0
        phase_imbalance_pct = (
            max(abs(value - avg_phase_kw) for value in phase_loads) / avg_phase_kw * 100.0
            if avg_phase_kw > 0.0
            else 0.0
        )

        power_factor = _combined_power_factor(total_site_kw, kvar_total)
        charging_share = charging_kw / total_site_kw if total_site_kw > 0.0 else 0.0
        weighted_current_thd = harmonic_source / charging_kw if charging_kw > 0.0 else 0.0
        thd_pct = min(
            12.0,
            site.background_thd_pct
            + 0.42 * weighted_current_thd * charging_share
            + 0.06 * max((load_ratio - 0.75) * 10.0, 0.0)
            + 0.03 * phase_imbalance_pct,
        )

        ramp_pct = abs(total_site_kw - previous_site_kw) / max(
            min(site.transformer_limit_kw, site.feeder_limit_kw), 1.0
        ) * 100.0
        voltage_drop = 0.004 + 0.035 * load_ratio + 0.004 * (phase_imbalance_pct / 3.0) + 0.0008 * ramp_pct
        voltage_pu = max(0.88, 1.0 - voltage_drop)
        previous_site_kw = total_site_kw

        if transformer_loading_pct > 100.0 or feeder_loading_pct > 100.0:
            risk_flags["overload_steps"] += 1
        if voltage_pu < 0.95:
            risk_flags["low_voltage_steps"] += 1
        if power_factor < 0.95:
            risk_flags["low_pf_steps"] += 1
        if phase_imbalance_pct > 2.5:
            risk_flags["high_imbalance_steps"] += 1
        if thd_pct > 5.0:
            risk_flags["high_thd_steps"] += 1

        timeline.append(
            {
                "minute": minute,
                "clock": _format_clock(minute),
                "charging_kw": round(charging_kw, 2),
                "site_kw": round(total_site_kw, 2),
                "active_sessions": len(active_states),
                "queued_sessions": len(queued),
                "transformer_loading_pct": round(transformer_loading_pct, 2),
                "feeder_loading_pct": round(feeder_loading_pct, 2),
                "voltage_pu": round(voltage_pu, 4),
                "power_factor": round(power_factor, 4),
                "phase_imbalance_pct": round(phase_imbalance_pct, 2),
                "thd_pct": round(thd_pct, 2),
            }
        )

    session_rows = []
    total_requested_kwh = sum(item.spec.requested_kwh for item in states)
    total_delivered_kwh = sum(item.delivered_kwh for item in states)

    for state in states:
        completion_pct = (
            state.delivered_kwh / state.spec.requested_kwh * 100.0 if state.spec.requested_kwh > 0.0 else 100.0
        )
        session_rows.append(
            {
                "session_id": state.spec.session_id,
                "vehicle": state.spec.vehicle_label,
                "mode": state.spec.required_mode.upper(),
                "arrival": _format_clock(state.spec.arrival_minute),
                "departure": _format_clock(state.spec.departure_minute),
                "requested_kwh": round(state.spec.requested_kwh, 1),
                "delivered_kwh": round(state.delivered_kwh, 1),
                "unmet_kwh": round(max(state.spec.requested_kwh - state.delivered_kwh, 0.0), 1),
                "completion_pct": round(completion_pct, 1),
                "wait_minutes": state.queue_minutes,
            }
        )

    session_rows.sort(key=lambda row: (row["unmet_kwh"], row["wait_minutes"], row["requested_kwh"]), reverse=True)
    summary = _build_summary(
        states=states,
        timeline=timeline,
        total_requested_kwh=total_requested_kwh,
        total_delivered_kwh=total_delivered_kwh,
        peak_queue=peak_queue,
        label=label or f"{POLICIES[policy_key]['label']} run",
    )
    headline = _build_headline(summary, risk_flags)

    return {
        "label": label or f"{POLICIES[policy_key]['label']} run",
        "policy": {"key": policy_key, **POLICIES[policy_key]},
        "site": asdict(site),
        "summary": summary,
        "headline": headline,
        "risk_flags": risk_flags,
        "takeaways": _build_takeaways(summary, risk_flags),
        "timeline": timeline,
        "top_sessions": session_rows[:10],
        "glossary": GLOSSARY,
    }


def _pick_connected(active_states: list[SessionState], connector_count: int) -> list[SessionState]:
    if connector_count <= 0:
        return []
    return active_states[:connector_count]


def _allocate_power(
    policy_key: str,
    minute: int,
    step_hours: float,
    connected_lookup: dict[str, SessionState],
    session_caps: dict[str, float],
    capacity_kw: float,
) -> dict[str, float]:
    if not session_caps or capacity_kw <= 0.0:
        return {session_id: 0.0 for session_id in connected_lookup}

    if policy_key == "uncontrolled":
        allocations = {session_id: 0.0 for session_id in connected_lookup}
        remaining = capacity_kw
        for session_id, cap in session_caps.items():
            grant = min(cap, remaining)
            allocations[session_id] = grant
            remaining -= grant
            if remaining <= 1e-9:
                break
        return allocations

    if policy_key == "equal_share":
        base = _waterfill_equal(session_caps, capacity_kw)
        return {session_id: round(base.get(session_id, 0.0), 4) for session_id in connected_lookup}

    weights: dict[str, float] = {}
    for session_id, state in connected_lookup.items():
        if session_id not in session_caps:
            continue
        time_left_hours = max((state.spec.departure_minute - minute) / 60.0, step_hours)
        required_average_power = state.energy_remaining_kwh / time_left_hours if time_left_hours > 0.0 else state.spec.max_power_kw
        urgency = required_average_power / max(session_caps[session_id], 1.0)
        arrival_age_hours = max((minute - state.spec.arrival_minute) / 60.0, 0.0)
        weights[session_id] = 1.0 + 2.8 * urgency + 0.25 * arrival_age_hours

    weighted = _waterfill_weighted(session_caps, weights, capacity_kw)
    return {session_id: round(weighted.get(session_id, 0.0), 4) for session_id in connected_lookup}


def _waterfill_equal(caps: dict[str, float], total_capacity: float) -> dict[str, float]:
    allocations = {session_id: 0.0 for session_id in caps}
    remaining = set(caps)
    leftover = total_capacity

    while remaining and leftover > 1e-9:
        share = leftover / len(remaining)
        distributed = 0.0
        saturated: list[str] = []

        for session_id in remaining:
            room = caps[session_id] - allocations[session_id]
            grant = min(room, share)
            allocations[session_id] += grant
            distributed += grant
            if room <= share + 1e-9:
                saturated.append(session_id)

        leftover -= distributed
        for session_id in saturated:
            remaining.remove(session_id)
        if distributed <= 1e-9:
            break

    return allocations


def _waterfill_weighted(
    caps: dict[str, float],
    weights: dict[str, float],
    total_capacity: float,
) -> dict[str, float]:
    allocations = {session_id: 0.0 for session_id in caps}
    remaining = {session_id for session_id, cap in caps.items() if cap > 0.0}
    leftover = total_capacity

    while remaining and leftover > 1e-9:
        weight_sum = sum(max(weights.get(session_id, 1.0), 0.01) for session_id in remaining)
        if weight_sum <= 0.0:
            return _waterfill_equal(caps, total_capacity)

        distributed = 0.0
        saturated: list[str] = []
        for session_id in remaining:
            share = leftover * max(weights.get(session_id, 1.0), 0.01) / weight_sum
            room = caps[session_id] - allocations[session_id]
            grant = min(room, share)
            allocations[session_id] += grant
            distributed += grant
            if room <= share + 1e-9:
                saturated.append(session_id)

        leftover -= distributed
        for session_id in saturated:
            remaining.remove(session_id)
        if distributed <= 1e-9:
            break

    return allocations


def _power_factor_for_session(session: ChargingSession, site: SiteConfig) -> float:
    if session.required_mode == "dc":
        return 0.99
    if site.ac_phases == 1 or session.phases == 1:
        return 0.965
    return 0.98


def _harmonic_emission_for_session(session: ChargingSession, site: SiteConfig) -> float:
    if session.required_mode == "dc":
        return 3.8
    if site.ac_phases == 1 or session.phases == 1:
        return 6.8
    return 4.6


def _reactive_power(power_kw: float, power_factor: float) -> float:
    power_factor = max(min(power_factor, 0.9999), 0.01)
    angle = math.acos(power_factor)
    return power_kw * math.tan(angle)


def _combined_power_factor(active_power_kw: float, reactive_power_kvar: float) -> float:
    if active_power_kw <= 0.0:
        return 1.0
    apparent = math.sqrt(active_power_kw ** 2 + reactive_power_kvar ** 2)
    return active_power_kw / apparent if apparent > 0.0 else 1.0


def _build_summary(
    *,
    states: list[SessionState],
    timeline: list[dict],
    total_requested_kwh: float,
    total_delivered_kwh: float,
    peak_queue: int,
    label: str,
) -> dict:
    completion_count = sum(
        1 for state in states if state.delivered_kwh + 0.1 >= state.spec.requested_kwh
    )
    avg_wait_minutes = sum(state.queue_minutes for state in states) / len(states) if states else 0.0
    peak_site_kw = max((row["site_kw"] for row in timeline), default=0.0)
    peak_transformer_loading_pct = max(
        (row["transformer_loading_pct"] for row in timeline), default=0.0
    )
    peak_feeder_loading_pct = max((row["feeder_loading_pct"] for row in timeline), default=0.0)
    min_voltage_pu = min((row["voltage_pu"] for row in timeline), default=1.0)
    worst_thd_pct = max((row["thd_pct"] for row in timeline), default=0.0)
    worst_imbalance_pct = max((row["phase_imbalance_pct"] for row in timeline), default=0.0)
    average_power_factor = (
        sum(row["power_factor"] for row in timeline) / len(timeline) if timeline else 1.0
    )

    return {
        "label": label,
        "session_count": len(states),
        "energy_requested_kwh": round(total_requested_kwh, 1),
        "energy_delivered_kwh": round(total_delivered_kwh, 1),
        "unmet_energy_kwh": round(max(total_requested_kwh - total_delivered_kwh, 0.0), 1),
        "completion_rate_pct": round(_safe_pct(completion_count, len(states)), 1),
        "average_wait_minutes": round(avg_wait_minutes, 1),
        "peak_queue": peak_queue,
        "peak_site_kw": round(peak_site_kw, 1),
        "peak_transformer_loading_pct": round(peak_transformer_loading_pct, 1),
        "peak_feeder_loading_pct": round(peak_feeder_loading_pct, 1),
        "min_voltage_pu": round(min_voltage_pu, 3),
        "average_power_factor": round(average_power_factor, 3),
        "worst_thd_pct": round(worst_thd_pct, 2),
        "worst_imbalance_pct": round(worst_imbalance_pct, 2),
    }


def _build_headline(summary: dict, risk_flags: dict[str, int]) -> str:
    if risk_flags["overload_steps"] > 0:
        return "The site overloaded at times, so this setup needs either more capacity or smarter charging control."
    if summary["min_voltage_pu"] < 0.95:
        return "Charging stayed mostly within limits, but voltage dipped enough to suggest local grid stress."
    if summary["worst_thd_pct"] > 5.0:
        return "The loading plan worked, but harmonic distortion became the main PQ concern."
    if summary["completion_rate_pct"] < 95.0:
        return "Grid limits were protected, but some vehicles did not receive all of the energy they wanted."
    return "This run stayed within the simplified site limits while serving most charging demand."


def _build_takeaways(summary: dict, risk_flags: dict[str, int]) -> list[str]:
    takeaways = [
        f"Peak site load reached {summary['peak_site_kw']:.1f} kW, and the worst transformer loading was {summary['peak_transformer_loading_pct']:.1f}%.",
        f"The lowest estimated voltage was {summary['min_voltage_pu']:.3f} p.u., while the worst THD estimate was {summary['worst_thd_pct']:.2f}%.",
        f"The site delivered {summary['energy_delivered_kwh']:.1f} of {summary['energy_requested_kwh']:.1f} kWh requested, with an average queue of {summary['average_wait_minutes']:.1f} minutes per vehicle.",
    ]

    if risk_flags["overload_steps"] > 0:
        takeaways.append(
            "Some time steps crossed a hard site limit. In simple terms, the grid connection was being asked to do too much."
        )
    elif summary["peak_transformer_loading_pct"] > 90.0:
        takeaways.append(
            "The site stayed under the hard limit, but it spent time close to it, so there is not much headroom."
        )

    if risk_flags["low_voltage_steps"] > 0:
        takeaways.append(
            "Voltage dipped below the usual comfort zone. That is a practical sign of local network stress."
        )
    if risk_flags["high_thd_steps"] > 0:
        takeaways.append(
            "The harmonic estimate crossed a common demonstration threshold, which is useful for explaining why charger mix matters."
        )
    if risk_flags["high_imbalance_steps"] > 0:
        takeaways.append(
            "Phase imbalance showed up, which can happen when single-phase charging is not spread evenly."
        )

    return takeaways


def _safe_pct(value: float, total: float) -> float:
    if total <= 0.0:
        return 0.0
    return value / total * 100.0


def _format_clock(minute: int) -> str:
    total_minutes = max(int(minute), 0)
    hours = (total_minutes // 60) % 24
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"

