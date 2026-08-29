from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from backend.app.common.time import as_utc
from backend.app.telemetry.values import MetricValue, finite_number

MetricKind = Literal["measurement", "state", "counter", "event"]
ValueType = Literal["number", "boolean", "string"]

FAST_FRESHNESS = timedelta(minutes=3)
SLOW_FRESHNESS = timedelta(minutes=15)
CHARGING_POWER_FLOOR_KW = 0.5
FRESHNESS_INTERVAL_MULTIPLIER = 3


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    value_type: ValueType
    unit: str | None
    meaning: str
    kind: MetricKind
    freshness: timedelta
    retain_stale: bool = False
    minimum: float | None = None
    maximum: float | None = None

    def validate(self, value: MetricValue) -> MetricValue | None:
        if value is None:
            return None
        if self.value_type == "boolean":
            return value if isinstance(value, bool) else None
        if self.value_type == "string":
            return value if isinstance(value, str) else None
        number = finite_number(value)
        if number is None:
            return None
        if self.minimum is not None and number < self.minimum:
            return None
        if self.maximum is not None and number > self.maximum:
            return None
        return number


def _number(
    key: str,
    unit: str,
    meaning: str,
    *,
    kind: MetricKind = "measurement",
    freshness: timedelta = SLOW_FRESHNESS,
    retain_stale: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        key,
        "number",
        unit,
        meaning,
        kind,
        freshness,
        retain_stale,
        minimum,
        maximum,
    )


CANONICAL_METRICS = {
    definition.key: definition
    for definition in (
        _number(
            "vehicle.speed",
            "km/h",
            "non-negative instantaneous road speed",
            freshness=FAST_FRESHNESS,
            minimum=0,
            maximum=1000,
        ),
        _number(
            "vehicle.odometer",
            "km",
            "cumulative vehicle distance",
            kind="counter",
            retain_stale=True,
            minimum=0,
        ),
        _number(
            "vehicle.range",
            "km",
            "estimated remaining vehicle range",
            kind="state",
            retain_stale=True,
            minimum=0,
        ),
        MetricDefinition(
            "vehicle.state",
            "string",
            None,
            "source-reported vehicle operating state",
            "state",
            SLOW_FRESHNESS,
            True,
        ),
        MetricDefinition(
            "vehicle.in_use",
            "boolean",
            None,
            "whether the vehicle is actively in use",
            "state",
            FAST_FRESHNESS,
        ),
        _number(
            "battery.soc",
            "%",
            "traction-battery state of charge from zero to one hundred",
            kind="state",
            retain_stale=True,
            minimum=0,
            maximum=100,
        ),
        _number(
            "battery.current",
            "A",
            "traction-battery current using the source profile sign convention",
            freshness=FAST_FRESHNESS,
        ),
        _number(
            "battery.pack_voltage",
            "V",
            "traction-battery pack voltage",
            freshness=FAST_FRESHNESS,
            minimum=0,
        ),
        _number(
            "battery.power",
            "kW",
            "positive while discharging and negative while absorbing energy",
            freshness=FAST_FRESHNESS,
        ),
        MetricDefinition(
            "charging.active",
            "boolean",
            None,
            "whether the vehicle is actively charging",
            "state",
            FAST_FRESHNESS,
        ),
        _number(
            "charging.power",
            "kW",
            "non-negative power entering the vehicle",
            freshness=FAST_FRESHNESS,
            minimum=0,
        ),
        _number(
            "charging.energy_added",
            "kWh",
            "cumulative energy added during a charging process",
            kind="counter",
            retain_stale=True,
            minimum=0,
        ),
        _number(
            "charging.voltage",
            "V",
            "charger input voltage",
            freshness=FAST_FRESHNESS,
            minimum=0,
        ),
        _number(
            "charging.current",
            "A",
            "charger input current",
            freshness=FAST_FRESHNESS,
            minimum=0,
        ),
        _number(
            "engine.rpm",
            "rpm",
            "engine or traction-machine rotational speed",
            freshness=FAST_FRESHNESS,
            minimum=0,
        ),
        _number(
            "engine.coolant_temperature",
            "°C",
            "coolant temperature",
            freshness=FAST_FRESHNESS,
            minimum=-100,
            maximum=300,
        ),
        MetricDefinition(
            "vehicle.door_open",
            "boolean",
            None,
            "whether a vehicle door is open",
            "state",
            FAST_FRESHNESS,
            True,
        ),
        MetricDefinition(
            "vehicle.lights",
            "string",
            None,
            "whether exterior lights are active",
            "state",
            FAST_FRESHNESS,
            True,
        ),
        MetricDefinition(
            "vehicle.high_beam",
            "boolean",
            None,
            "whether high-beam lights are active",
            "state",
            FAST_FRESHNESS,
            True,
        ),
        MetricDefinition(
            "vehicle.handbrake",
            "boolean",
            None,
            "whether the parking brake is active",
            "state",
            FAST_FRESHNESS,
            True,
        ),
        MetricDefinition(
            "tyre.warning",
            "boolean",
            None,
            "whether the tyre-pressure system reports a warning",
            "state",
            SLOW_FRESHNESS,
            True,
        ),
        *(
            _number(
                f"tyre.{corner}_{quantity}",
                unit,
                f"{corner.replace('_', ' ')} tyre {quantity}",
                retain_stale=True,
                minimum=0 if quantity == "pressure" else -100,
                maximum=1000 if quantity == "pressure" else 300,
            )
            for corner in ("front_left", "front_right", "rear_left", "rear_right")
            for quantity, unit in (("pressure", "bar"), ("temperature", "°C"))
        ),
    )
}


def definition_for(key: str) -> MetricDefinition | None:
    return CANONICAL_METRICS.get(key)


def observation_is_fresh(
    key: str,
    observed_at: datetime,
    now: datetime,
    *,
    reporting_interval: int | None = None,
    event_driven: bool = False,
    source_last_contact_at: datetime | None = None,
    source_liveness_window_seconds: int | None = None,
) -> bool:
    definition = definition_for(key)
    freshness = definition.freshness if definition else SLOW_FRESHNESS
    if event_driven and source_last_contact_at is not None:
        liveness = timedelta(seconds=source_liveness_window_seconds or 0)
        return as_utc(source_last_contact_at) >= as_utc(now) - max(freshness, liveness)
    if reporting_interval is not None:
        freshness = max(
            freshness,
            timedelta(seconds=FRESHNESS_INTERVAL_MULTIPLIER * reporting_interval),
        )
    return as_utc(observed_at) >= as_utc(now) - freshness


def normalize_value(key: str, value: MetricValue) -> tuple[bool, MetricValue]:
    if value is None:
        return True, None
    definition = definition_for(key)
    if definition is None:
        return True, value
    normalized = definition.validate(value)
    return normalized is not None, normalized
