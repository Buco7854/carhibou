import json
import math
import re
from dataclasses import dataclass, field

from backend.app.telemetry.schemas import MetricValue
from backend.app.vehicle_profiles.schemas import (
    PROFILE_DEFINITION_ADAPTER,
    MappingProfileDefinition,
    MappingRule,
)

NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
POSITION_RANGES = {
    "latitude": (-90.0, 90.0),
    "longitude": (-180.0, 180.0),
    "altitude": (-500.0, 15000.0),
    "speed": (0.0, 1000.0),
    "heading": (0.0, 360.0),
    "accuracy": (0.0, math.inf),
}


@dataclass
class MappedValue:
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    position: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


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
    if NUMBER.fullmatch(cleaned):
        number = float(cleaned)
        return number if math.isfinite(number) else None
    return cleaned


def _number(value: object) -> float | None:
    coerced = coerce_value(value)
    if isinstance(coerced, bool) or not isinstance(coerced, float):
        return None
    return coerced


def _json_object(value: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _valid_metric_key(value: str) -> bool:
    return bool(value and len(value) <= 120 and not any(char.isspace() for char in value))


class MappingEngine:
    def __init__(self, definition: MappingProfileDefinition | dict[str, object]) -> None:
        if isinstance(definition, MappingProfileDefinition):
            self.definition = definition
        else:
            parsed = PROFILE_DEFINITION_ADAPTER.validate_python(definition)
            if not isinstance(parsed, MappingProfileDefinition):
                raise ValueError("mapping engine requires a mapping profile")
            self.definition = parsed
        self._rules = {rule.match: rule for rule in self.definition.rules}
        self._ignored = set(self.definition.ignore)

    def map(self, key: str, payload: bytes | str) -> MappedValue:
        result = MappedValue()
        if not _valid_metric_key(key) or "/" in key:
            result.errors.append("invalid source key")
            return result
        if key in self._ignored:
            return result
        try:
            value = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        except UnicodeDecodeError:
            result.errors.append(f"{key}: payload is not UTF-8")
            return result
        value = value.strip()
        if not value or value.lower() == "nil":
            return result
        rule = self._rules.get(key)
        if rule:
            self._apply_rule(result, rule, value)
        elif self.definition.passthrough_prefix:
            self._passthrough(result, key, value)
        return result

    def _apply_rule(self, result: MappedValue, rule: MappingRule, value: str) -> None:
        transform = rule.transform
        if transform and transform.json_flatten:
            parsed = _json_object(value)
            if parsed is None:
                result.errors.append(f"{rule.match}: expected a JSON object")
                return
            if rule.target == "position":
                self._position_object(result, rule.match, parsed)
            else:
                self._flatten(result, rule.target, parsed)
            return
        if transform and transform.enum is not None:
            mapped = transform.enum.get(value, transform.enum.get("*"))
            if mapped is None:
                result.errors.append(f"{rule.match}: value is not mapped")
                return
            self._store(result, rule, mapped)
            return
        if transform and transform.boolean:
            self._store(result, rule, value.lower() in {"1", "true", "yes", "on"})
            return
        if transform and (transform.scale is not None or transform.offset is not None):
            number = _number(value)
            if number is None:
                result.errors.append(f"{rule.match}: expected a number")
                return
            mapped = number * (transform.scale if transform.scale is not None else 1)
            mapped += transform.offset if transform.offset is not None else 0
            self._store(result, rule, mapped)
            return
        self._store(
            result,
            rule,
            value if rule.target == "vehicle.state" else coerce_value(value),
        )

    def _store(self, result: MappedValue, rule: MappingRule, value: MetricValue) -> None:
        if value is None:
            return
        if rule.target.startswith("position."):
            name = rule.target.removeprefix("position.")
            number = _number(value)
            bounds = POSITION_RANGES[name]
            if (
                number is None
                or not bounds[0] <= number <= bounds[1]
                or (name == "heading" and number == bounds[1])
            ):
                result.errors.append(f"{rule.match}: position value is invalid")
                return
            result.position[name] = number
            return
        result.metrics[rule.target] = value

    def _position_object(self, result: MappedValue, source: str, values: dict[str, object]) -> None:
        position: dict[str, float] = {}
        found = False
        for name, bounds in POSITION_RANGES.items():
            if name not in values:
                continue
            found = True
            number = _number(values[name])
            if (
                number is None
                or not bounds[0] <= number <= bounds[1]
                or (name == "heading" and number == bounds[1])
            ):
                result.errors.append(f"{source}: position field {name} is invalid")
                continue
            position[name] = number
        if not found:
            result.errors.append(f"{source}: position object has no supported fields")
            return
        if ("latitude" in position) != ("longitude" in position):
            result.errors.append(f"{source}: latitude and longitude must be provided together")
            position.pop("latitude", None)
            position.pop("longitude", None)
        result.position.update(position)

    def _flatten(self, result: MappedValue, prefix: str, values: dict[str, object]) -> None:
        for key, raw in values.items():
            metric_key = f"{prefix}.{key}"
            if not isinstance(key, str) or not _valid_metric_key(metric_key):
                continue
            coerced = coerce_value(raw)
            if coerced is not None:
                result.metrics[metric_key] = coerced

    def _passthrough(self, result: MappedValue, key: str, value: str) -> None:
        prefix = f"{self.definition.passthrough_prefix}.{key}"
        if value.startswith("{"):
            parsed = _json_object(value)
            if parsed is None:
                result.errors.append(f"{key}: expected a JSON object")
                return
            self._flatten(result, prefix, parsed)
            return
        if not _valid_metric_key(prefix):
            result.errors.append(f"{key}: mapped key is too long")
            return
        coerced = coerce_value(value)
        if coerced is not None:
            result.metrics[prefix] = coerced
