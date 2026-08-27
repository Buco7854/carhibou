import math
import re
from dataclasses import dataclass

MetricValue = float | int | bool | str | None
NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


@dataclass(frozen=True)
class NumericRange:
    minimum: float
    maximum: float
    maximum_exclusive: bool = False

    def contains(self, value: float) -> bool:
        upper = value < self.maximum if self.maximum_exclusive else value <= self.maximum
        return self.minimum <= value and upper


POSITION_RANGES = {
    "latitude": NumericRange(-90.0, 90.0),
    "longitude": NumericRange(-180.0, 180.0),
    "altitude": NumericRange(-500.0, 15000.0),
    "speed": NumericRange(0.0, 1000.0),
    "heading": NumericRange(0.0, 360.0, maximum_exclusive=True),
    "accuracy": NumericRange(0.0, 100000.0),
}


def finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def coerce_metric_value(value: object) -> MetricValue:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return finite_number(value)
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
        return finite_number(float(cleaned))
    return cleaned


def coerce_number(value: object) -> float | None:
    return finite_number(coerce_metric_value(value))
