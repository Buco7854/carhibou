import json
import math
import re
from dataclasses import dataclass, field

from backend.app.telemetry.schemas import MetricValue

TESLAMATE_TOPICS = (
    "display_name",
    "state",
    "since",
    "healthy",
    "version",
    "update_available",
    "update_version",
    "download_perc",
    "install_perc",
    "model",
    "trim_badging",
    "exterior_color",
    "wheel_type",
    "spoiler_type",
    "geofence",
    "latitude",
    "longitude",
    "location",
    "shift_state",
    "power",
    "speed",
    "heading",
    "elevation",
    "locked",
    "sentry_mode",
    "windows_open",
    "driver_front_window_open",
    "driver_rear_window_open",
    "passenger_front_window_open",
    "passenger_rear_window_open",
    "doors_open",
    "driver_front_door_open",
    "driver_rear_door_open",
    "passenger_front_door_open",
    "passenger_rear_door_open",
    "sun_roof_state",
    "sun_roof_installed",
    "sun_roof_percent_open",
    "trunk_open",
    "frunk_open",
    "is_user_present",
    "is_climate_on",
    "inside_temp",
    "outside_temp",
    "is_preconditioning",
    "odometer",
    "est_battery_range_km",
    "rated_battery_range_km",
    "ideal_battery_range_km",
    "battery_level",
    "usable_battery_level",
    "plugged_in",
    "charging_state",
    "charge_energy_added",
    "charge_limit_soc",
    "charge_port_door_open",
    "charger_actual_current",
    "charger_phases",
    "charger_power",
    "charger_voltage",
    "charge_current_request",
    "charge_current_request_max",
    "scheduled_charging_start_time",
    "time_to_full_charge",
    "tpms_pressure_fl",
    "tpms_pressure_fr",
    "tpms_pressure_rl",
    "tpms_pressure_rr",
    "tpms_soft_warning_fl",
    "tpms_soft_warning_fr",
    "tpms_soft_warning_rl",
    "tpms_soft_warning_rr",
    "active_route_destination",
    "active_route_latitude",
    "active_route_longitude",
    "active_route",
    "center_display_state",
    "service_mode",
)

DEPRECATED_TOPICS = {
    "latitude",
    "longitude",
    "active_route_destination",
    "active_route_latitude",
    "active_route_longitude",
}
NUMERIC_METRICS = {
    "battery_level": "battery.soc",
    "power": "battery.power",
    "odometer": "vehicle.odometer",
    "charger_power": "charging.power",
    "est_battery_range_km": "vehicle.range",
    "tpms_pressure_fl": "tyre.front_left_pressure",
    "tpms_pressure_fr": "tyre.front_right_pressure",
    "tpms_pressure_rl": "tyre.rear_left_pressure",
    "tpms_pressure_rr": "tyre.rear_right_pressure",
}
POSITION_TOPICS = {
    "elevation": "altitude",
    "heading": "heading",
    "speed": "speed",
}
NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


@dataclass
class MappedValue:
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    position: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _float(value: str) -> float | None:
    if not NUMBER.fullmatch(value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def coerce_value(value: object) -> MetricValue:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() == "nil":
        return None
    if cleaned.lower() == "true":
        return True
    if cleaned.lower() == "false":
        return False
    parsed_number = _float(cleaned)
    return parsed_number if parsed_number is not None else cleaned


def _numeric(topic: str, value: str, target: str, *, position: bool) -> MappedValue:
    result = MappedValue()
    number = _float(value)
    if number is None:
        result.errors.append(f"{topic}: expected a number")
    elif position:
        result.position[target] = number
    else:
        result.metrics[target] = number
    return result


def _json_object(topic: str, value: str) -> tuple[dict[str, object] | None, MappedValue]:
    result = MappedValue()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        result.errors.append(f"{topic}: expected a JSON object")
        return None, result
    if not isinstance(parsed, dict):
        result.errors.append(f"{topic}: expected a JSON object")
        return None, result
    return parsed, result


def map_message(topic: str, payload: bytes | str) -> MappedValue:
    result = MappedValue()
    if (
        not topic
        or "/" in topic
        or any(char.isspace() for char in topic)
        or len(f"teslamate.{topic}") > 120
    ):
        result.errors.append("invalid topic key")
        return result
    if topic in DEPRECATED_TOPICS:
        return result
    try:
        value = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    except UnicodeDecodeError:
        result.errors.append(f"{topic}: payload is not UTF-8")
        return result
    value = value.strip()
    if not value or value.lower() == "nil":
        return result

    target = NUMERIC_METRICS.get(topic)
    if target:
        return _numeric(topic, value, target, position=False)
    target = POSITION_TOPICS.get(topic)
    if target:
        result = _numeric(topic, value, target, position=True)
        number = result.position.get(target)
        out_of_range = number is not None and (
            (target == "altitude" and not -500 <= number <= 15000)
            or (target == "heading" and not 0 <= number < 360)
            or (target == "speed" and not 0 <= number <= 1000)
        )
        if out_of_range:
            result.position.clear()
            result.errors.append(f"{topic}: value is out of range")
        return result
    if topic == "state":
        result.metrics["vehicle.state"] = value
        return result
    if topic == "charging_state":
        normalized = value.lower()
        if normalized == "charging":
            result.metrics["charging.active"] = True
        elif normalized in {"disconnected", "starting", "stopped", "nopower", "complete"}:
            result.metrics["charging.active"] = False
        else:
            result.errors.append("charging_state: unknown state")
        return result
    if topic == "location":
        parsed, result = _json_object(topic, value)
        if parsed is None:
            return result
        latitude = coerce_value(parsed.get("latitude"))
        longitude = coerce_value(parsed.get("longitude"))
        if not isinstance(latitude, float) or not isinstance(longitude, float):
            result.errors.append("location: latitude and longitude must be numbers")
            return result
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            result.errors.append("location: coordinates are out of range")
            return result
        result.position.update(latitude=latitude, longitude=longitude)
        return result
    if topic == "active_route" or value.startswith("{"):
        parsed, result = _json_object(topic, value)
        if parsed is None:
            return result
        for key, raw in parsed.items():
            metric_key = f"teslamate.{topic}.{key}"
            if (
                not isinstance(key, str)
                or not key
                or any(char.isspace() for char in key)
                or len(metric_key) > 120
            ):
                continue
            coerced = coerce_value(raw)
            if coerced is not None:
                result.metrics[metric_key] = coerced
        return result

    coerced = coerce_value(value)
    if coerced is not None:
        result.metrics[f"teslamate.{topic}"] = coerced
    return result
