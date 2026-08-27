import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agent.vehicle_agent.models import PositionFix, Sample


@dataclass(frozen=True)
class JourneyPoint:
    latitude: float
    longitude: float
    speed: float
    soc: float
    battery_current: float
    charging: bool
    mobile_signal: int


class SimulatedCZeroJourney:
    """Deterministic stationary-drive-stop-charge journey around demo coordinates."""

    center_latitude = 48.8566
    center_longitude = 2.3522

    def __init__(self, samples: int = 120):
        self.samples = max(samples, 20)

    def point(self, index: int) -> JourneyPoint:
        progress = min(max(index / (self.samples - 1), 0), 1)
        if progress < 0.1:
            route_progress, speed, current, charging = 0.0, 0.0, 0.0, False
        elif progress < 0.7:
            route_progress = (progress - 0.1) / 0.6
            speed = 25 + 30 * abs(math.sin(route_progress * math.pi * 3))
            current = -18 - speed * 0.45
            charging = False
        elif progress < 0.82:
            route_progress, speed, current, charging = 1.0, 0.0, 0.0, False
        else:
            route_progress, speed, current, charging = 1.0, 0.0, 18.0, True
        latitude = self.center_latitude + route_progress * 0.018
        longitude = self.center_longitude + math.sin(route_progress * math.pi) * 0.012
        drive_loss = min(route_progress * 16, 16)
        charge_gain = max(0.0, progress - 0.82) / 0.18 * 8
        soc = 82 - drive_loss + charge_gain
        return JourneyPoint(
            latitude,
            longitude,
            speed,
            soc,
            current,
            charging,
            -75 - int(12 * abs(math.sin(progress * math.pi * 2))),
        )

    def sample(self, index: int, boot_time: datetime | None = None) -> Sample:
        point = self.point(index)
        recorded_at = (boot_time or datetime.now(UTC)) + timedelta(seconds=index * 5)
        heading = 35 if point.speed else 0
        return Sample(
            sequence=index,
            recorded_at=recorded_at,
            position=PositionFix(
                latitude=point.latitude,
                longitude=point.longitude,
                altitude=38,
                speed=point.speed,
                heading=heading,
                accuracy=5,
                fix_quality=1,
                satellites=9,
            ),
            metrics={
                "battery.soc": round(point.soc, 2),
                "battery.pack_voltage": 330.0,
                "battery.current": round(point.battery_current, 2),
                "battery.power": round(330 * point.battery_current / 1000, 2),
                "vehicle.speed": round(point.speed, 2),
                "charging.active": point.charging,
                "charging.power": 5.9 if point.charging else 0,
            },
            agent={"mobile_signal": point.mobile_signal, "provider": "simulator"},
        )

    def __iter__(self):  # type: ignore[no-untyped-def]
        boot_time = datetime.now(UTC) - timedelta(seconds=(self.samples - 1) * 5)
        for index in range(self.samples):
            yield self.sample(index, boot_time)
