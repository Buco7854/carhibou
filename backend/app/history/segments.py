from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.app.access.dependencies import ViewVehicle
from backend.app.auth.dependencies import Db
from backend.app.common.time import as_utc, utcnow
from backend.app.history.schemas import (
    ChargeSegment,
    DriveSegment,
    SegmentPosition,
    SegmentsResponse,
)
from backend.app.telemetry.models import Telemetry
from backend.app.telemetry.values import finite_number

router = APIRouter(prefix="/vehicles/{vehicle_id}/segments", tags=["history"])
JOIN_GAP = timedelta(seconds=180)
MINIMUM_SEGMENT = timedelta(seconds=60)
MAXIMUM_RANGE = timedelta(days=92)
DRIVING_STATES = {"drive", "driving", "moving", "ready", "in_use"}
# Below 0.5 kW, charger readings overlap with parked pack noise and auxiliary loads.
CHARGING_POWER_FLOOR_KW = 0.5


def _position(row: Telemetry) -> SegmentPosition | None:
    if row.latitude is None or row.longitude is None:
        return None
    return SegmentPosition(latitude=row.latitude, longitude=row.longitude)


def _distance(left: SegmentPosition, right: SegmentPosition) -> float:
    earth_km = 6371.0088
    latitude = radians(right.latitude - left.latitude)
    longitude = radians(right.longitude - left.longitude)
    start = radians(left.latitude)
    end = radians(right.latitude)
    value = sin(latitude / 2) ** 2 + cos(start) * cos(end) * sin(longitude / 2) ** 2
    return 2 * earth_km * asin(sqrt(value))


def _drive_signal(row: Telemetry) -> bool | None:
    # A charge is never a drive, even if a vehicle keeps READY asserted while
    # plugged in. The explicit charging state outranks every motion fallback.
    if _charge_signal(row) is True:
        return False
    in_use = row.metrics.get("vehicle.in_use")
    if isinstance(in_use, bool):
        return in_use
    agent_data = row.agent_data if isinstance(row.agent_data, dict) else {}
    agent_in_use = agent_data.get("vehicle_in_use")
    if isinstance(agent_in_use, bool):
        return agent_in_use
    ready = row.metrics.get("vehicle.ready")
    if isinstance(ready, bool):
        return ready
    return None


def _drive_evidence(row: Telemetry, previous: Telemetry | None) -> bool:
    signal = _drive_signal(row)
    if signal is not None:
        return signal
    state = row.metrics.get("vehicle.state")
    if isinstance(state, str) and state.strip().lower() in DRIVING_STATES:
        return True
    speed = finite_number(row.metrics.get("vehicle.speed"))
    if speed is not None and speed > 1:
        return True
    if row.gps_speed is not None and row.gps_speed > 1:
        return True
    charging = row.metrics.get("charging.active")
    current_position = _position(row)
    previous_position = _position(previous) if previous else None
    return bool(
        charging is False
        and current_position
        and previous_position
        and _distance(previous_position, current_position) > 0
    )


def _charge_signal(row: Telemetry) -> bool | None:
    active = row.metrics.get("charging.active")
    if isinstance(active, bool):
        return active
    power = finite_number(row.metrics.get("charging.power"))
    if power is not None:
        return power >= CHARGING_POWER_FLOOR_KW
    return None


def _charge_evidence(row: Telemetry) -> bool:
    return _charge_signal(row) is True


def _drive_groups(rows: list[Telemetry]) -> list[list[Telemetry]]:
    groups: list[list[Telemetry]] = []
    start: int | None = None
    last_evidence: int | None = None
    signal_bounded = False

    for index, row in enumerate(rows):
        signal = _drive_signal(row)
        if signal is False:
            if start is not None and last_evidence is not None:
                # A false signal closes a signal-bounded drive at the actual
                # parked reading. A fallback-only drive still ends where its
                # last motion evidence ended; the later false cannot date it.
                end = index if signal_bounded else last_evidence
                groups.append(rows[start : end + 1])
            start = None
            last_evidence = None
            signal_bounded = False
            continue

        previous = rows[index - 1] if index else None
        active = signal is True or (signal is None and _drive_evidence(row, previous))
        if not active:
            continue
        if start is None:
            start = index
        elif not signal_bounded and last_evidence is not None:
            gap = as_utc(row.recorded_at) - as_utc(rows[last_evidence].recorded_at)
            if gap >= JOIN_GAP:
                groups.append(rows[start : last_evidence + 1])
                start = index
        last_evidence = index
        signal_bounded = signal_bounded or signal is True

    if start is not None and last_evidence is not None:
        groups.append(rows[start : last_evidence + 1])
    return groups


def _charge_groups(rows: list[Telemetry]) -> list[list[Telemetry]]:
    groups: list[list[Telemetry]] = []
    start: int | None = None
    last_charging: int | None = None

    for index, row in enumerate(rows):
        signal = _charge_signal(row)
        if signal is True:
            if start is None:
                start = index
            last_charging = index
        elif signal is False and start is not None and last_charging is not None:
            # Include the stop reading: it dates plug-out and may carry the
            # final SOC or accumulated-energy value for the session.
            groups.append(rows[start : index + 1])
            start = None
            last_charging = None

    if start is not None and last_charging is not None:
        groups.append(rows[start : last_charging + 1])
    return groups


def _metric_edges(rows: list[Telemetry], key: str) -> tuple[float | None, float | None]:
    values = [finite_number(row.metrics.get(key)) for row in rows]
    present = [value for value in values if value is not None]
    return (present[0], present[-1]) if len(present) >= 2 else (None, None)


def _positions(rows: list[Telemetry]) -> list[SegmentPosition]:
    return [position for row in rows if (position := _position(row)) is not None]


def _distance_km(rows: list[Telemetry]) -> float | None:
    start, end = _metric_edges(rows, "vehicle.odometer")
    if start is not None and end is not None and end >= start:
        return end - start
    positions = _positions(rows)
    if len(positions) < 2:
        return None
    return sum(
        _distance(left, right) for left, right in zip(positions, positions[1:], strict=False)
    )


def _speeds(rows: list[Telemetry]) -> list[float]:
    values = []
    for row in rows:
        speed = finite_number(row.metrics.get("vehicle.speed"))
        if speed is None:
            speed = row.gps_speed
        if speed is not None:
            values.append(speed)
    return values


def _has_motion(rows: list[Telemetry]) -> bool:
    odometer_start, odometer_end = _metric_edges(rows, "vehicle.odometer")
    if odometer_start is not None and odometer_end is not None and odometer_end > odometer_start:
        return True
    if any(
        (speed := finite_number(row.metrics.get("vehicle.speed"))) is not None
        and speed > 1
        or row.gps_speed is not None
        and row.gps_speed > 1
        for row in rows
    ):
        return True
    positions = _positions(rows)
    return any(
        _distance(left, right) > 0 for left, right in zip(positions, positions[1:], strict=False)
    )


def _unreported_seconds(rows: list[Telemetry]) -> float:
    unreported = 0.0
    for left, right in zip(rows, rows[1:], strict=False):
        gap = (as_utc(right.recorded_at) - as_utc(left.recorded_at)).total_seconds()
        expected = left.reporting_interval or int(JOIN_GAP.total_seconds())
        if gap > expected * 3:
            unreported += gap
    return unreported


def _power_integral(rows: list[Telemetry]) -> tuple[float | None, float | None]:
    energy = 0.0
    seconds = 0.0
    power = None
    for left, right in zip(rows, rows[1:], strict=False):
        current = finite_number(left.metrics.get("charging.power"))
        if current is not None:
            power = current
        if power is None:
            continue
        interval = (as_utc(right.recorded_at) - as_utc(left.recorded_at)).total_seconds()
        if interval <= 0:
            continue
        energy += power * interval / 3600
        seconds += interval
    if not seconds:
        return None, None
    return energy, energy / (seconds / 3600)


def _drive_segment(rows: list[Telemetry], capacity: float | None) -> DriveSegment | None:
    start = as_utc(rows[0].recorded_at)
    end = as_utc(rows[-1].recorded_at)
    duration = end - start
    if duration < MINIMUM_SEGMENT or not _has_motion(rows):
        return None
    positions = _positions(rows)
    # A final false lifecycle reading dates the parked boundary but is not part
    # of the drive's speed population. This also keeps a contradictory stale
    # speed on an authoritative parked reading from becoming the trip maximum.
    speed_rows = rows[:-1] if _drive_signal(rows[-1]) is False else rows
    speeds = _speeds(speed_rows)
    soc_start, soc_end = _metric_edges(rows, "battery.soc")
    energy = None
    if capacity is not None and soc_start is not None and soc_end is not None:
        energy = capacity * (soc_start - soc_end) / 100
    return DriveSegment(
        start=start,
        end=end,
        duration_seconds=duration.total_seconds(),
        unreported_seconds=_unreported_seconds(rows),
        start_position=positions[0] if positions else None,
        end_position=positions[-1] if positions else None,
        distance_km=_distance_km(rows),
        avg_speed=sum(speeds) / len(speeds) if speeds else None,
        max_speed=max(speeds) if speeds else None,
        soc_start=soc_start,
        soc_end=soc_end,
        energy_kwh=energy,
    )


def _charge_segment(rows: list[Telemetry]) -> ChargeSegment | None:
    start = as_utc(rows[0].recorded_at)
    end = as_utc(rows[-1].recorded_at)
    if end - start < MINIMUM_SEGMENT:
        return None
    soc_start, soc_end = _metric_edges(rows, "battery.soc")
    added_start, added_end = _metric_edges(rows, "charging.energy_added")
    integrated, average = _power_integral(rows)
    energy = (
        added_end - added_start
        if added_start is not None and added_end is not None and added_end >= added_start
        else integrated
    )
    powers = [
        power
        for row in rows
        if (power := finite_number(row.metrics.get("charging.power"))) is not None
    ]
    positions = _positions(rows)
    return ChargeSegment(
        start=start,
        end=end,
        duration_seconds=(end - start).total_seconds(),
        unreported_seconds=_unreported_seconds(rows),
        position=positions[0] if positions else None,
        soc_start=soc_start,
        soc_end=soc_end,
        energy_kwh=energy,
        peak_power=max(powers) if powers else None,
        avg_power=average,
    )


@router.get("", response_model=SegmentsResponse, response_model_exclude_none=True)
def segments(
    vehicle_id: str,
    start: datetime,
    db: Db,
    authorized: ViewVehicle,
    end: datetime | None = None,
) -> SegmentsResponse:
    resolved_start = as_utc(start)
    resolved_end = as_utc(end) if end else utcnow()
    if resolved_start >= resolved_end:
        raise HTTPException(status_code=400, detail="start must be earlier than end")
    if resolved_end - resolved_start > MAXIMUM_RANGE:
        raise HTTPException(status_code=400, detail="segment range cannot exceed 92 days")
    rows = list(
        db.scalars(
            select(Telemetry)
            .where(
                Telemetry.vehicle_id == vehicle_id,
                Telemetry.recorded_at >= resolved_start,
                Telemetry.recorded_at < resolved_end,
            )
            .order_by(Telemetry.recorded_at, Telemetry.sequence, Telemetry.id)
        )
    )
    drives = [
        segment
        for group in _drive_groups(rows)
        if (segment := _drive_segment(group, authorized.vehicle.battery_nominal_capacity_kwh))
        is not None
    ]
    charges = [
        charge_segment
        for group in _charge_groups(rows)
        if (charge_segment := _charge_segment(group)) is not None
    ]
    return SegmentsResponse(drives=drives, charges=charges)
