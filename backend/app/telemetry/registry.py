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
            "how fast the vehicle is moving",
            freshness=FAST_FRESHNESS,
            minimum=0,
            maximum=1000,
        ),
        _number(
            "vehicle.odometer",
            "km",
            "total distance the vehicle has travelled",
            kind="counter",
            retain_stale=True,
            minimum=0,
        ),
        _number(
            "vehicle.range",
            "km",
            "how far the vehicle estimates it can still go",
            kind="state",
            retain_stale=True,
            minimum=0,
        ),
        MetricDefinition(
            "vehicle.state",
            "string",
            None,
            "the operating state the vehicle reports for itself",
            "state",
            SLOW_FRESHNESS,
            True,
        ),
        MetricDefinition(
            "vehicle.ready",
            "boolean",
            None,
            "whether the vehicle is switched on and able to move",
            "state",
            FAST_FRESHNESS,
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
            "how much charge is left in the main battery, from zero to one hundred",
            kind="state",
            retain_stale=True,
            minimum=0,
            maximum=100,
        ),
        _number(
            "battery.current",
            "A",
            "current flowing into or out of the main battery",
            freshness=FAST_FRESHNESS,
        ),
        _number(
            "battery.pack_voltage",
            "V",
            "voltage of the main battery that drives the wheels",
            freshness=FAST_FRESHNESS,
            minimum=0,
        ),
        _number(
            "battery.aux_voltage",
            "V",
            "voltage of the small battery that powers the lights, locks and electronics",
            kind="state",
            retain_stale=True,
            minimum=0,
            maximum=30,
        ),
        _number(
            "battery.power",
            "kW",
            "power the main battery is delivering, negative while it is charging",
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
            "power coming from the charger into the vehicle",
            freshness=FAST_FRESHNESS,
            minimum=0,
        ),
        _number(
            "charging.energy_added",
            "kWh",
            "energy added so far in this charge",
            kind="counter",
            retain_stale=True,
            minimum=0,
        ),
        _number(
            "charging.voltage",
            "V",
            "voltage coming from the charger",
            freshness=FAST_FRESHNESS,
            minimum=0,
        ),
        _number(
            "charging.current",
            "A",
            "current coming from the charger",
            freshness=FAST_FRESHNESS,
            minimum=0,
        ),
        _number(
            "engine.rpm",
            "rpm",
            "how fast the engine or motor is turning",
            freshness=FAST_FRESHNESS,
            minimum=0,
        ),
        _number(
            "engine.load",
            "%",
            "how hard the engine is working, as a share of its maximum",
            freshness=FAST_FRESHNESS,
            minimum=0,
            maximum=100,
        ),
        _number(
            "engine.throttle",
            "%",
            "how far the throttle is open",
            freshness=FAST_FRESHNESS,
            minimum=0,
            maximum=100,
        ),
        _number(
            "engine.maf",
            "g/s",
            "how much air the engine is drawing in each second",
            freshness=FAST_FRESHNESS,
            minimum=0,
            maximum=1000,
        ),
        _number(
            "engine.intake_temperature",
            "°C",
            "temperature of the air entering the engine",
            freshness=FAST_FRESHNESS,
            minimum=-100,
            maximum=300,
        ),
        _number(
            "fuel.level",
            "%",
            "usable fuel remaining in the tank from empty to full",
            kind="state",
            retain_stale=True,
            minimum=0,
            maximum=100,
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


@dataclass(frozen=True)
class PositionField:
    key: str
    unit: str
    meaning: str


# A fix is one observation, not six metrics: its fields are only true together,
# so they are described here rather than in CANONICAL_METRICS and must never be
# resolved, aggregated or carried forward independently of one another.
POSITION_MEANING = (
    "the vehicle's location, recorded as one whole: latitude, longitude, altitude, "
    "speed, heading and accuracy always come from the same moment and are never "
    "mixed between moments"
)

POSITION_FIELDS = (
    PositionField("latitude", "°", "how far north or south of the equator, in degrees"),
    PositionField("longitude", "°", "how far east or west of the prime meridian, in degrees"),
    PositionField(
        "altitude", "m", "the vehicle's height above sea level, as the receiver reports it"
    ),
    PositionField(
        "speed",
        "km/h",
        "how fast the vehicle is moving, measured by the receiver rather than the vehicle",
    ),
    PositionField(
        "heading", "°", "the direction the vehicle is travelling, in degrees clockwise from north"
    ),
    PositionField("accuracy", "m", "how far the real location could be from this one"),
)


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
