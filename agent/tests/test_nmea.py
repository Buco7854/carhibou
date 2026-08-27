import pytest

from agent.vehicle_agent.providers.nmea import NMEAAccumulator, NMEAError, parse_nmea


def sentence(body: str) -> str:
    checksum = 0
    for character in body:
        checksum ^= ord(character)
    return f"${body}*{checksum:02X}"


def test_rmc_position_speed_heading_and_timestamp() -> None:
    fix = parse_nmea("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A")
    assert fix is not None
    assert fix.latitude == pytest.approx(48.1173)
    assert fix.longitude == pytest.approx(11.5166667)
    assert fix.speed == pytest.approx(41.4848)
    assert fix.heading == 84.4
    assert fix.recorded_at is not None and fix.recorded_at.year == 1994


def test_gga_quality_altitude_and_satellites() -> None:
    fix = parse_nmea("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47")
    assert fix is not None
    assert fix.altitude == 545.4
    assert fix.fix_quality == 1
    assert fix.satellites == 8


def test_invalid_fix_is_never_returned_as_position() -> None:
    invalid = sentence("GPRMC,123519,V,4807.038,N,01131.000,E,0,0,230394,,,A")
    assert parse_nmea(invalid) is None
    with pytest.raises(NMEAError, match="checksum"):
        parse_nmea(invalid[:-2] + "00")


def test_gst_accuracy_is_attached_to_last_valid_fix() -> None:
    parser = NMEAAccumulator()
    parser.consume("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47")
    fix = parser.consume(sentence("GPGST,123520.00,3.2,6.6,4.7,47.3,5.8,5.6,22.4"))
    assert fix is not None
    assert fix.accuracy == pytest.approx((5.8**2 + 5.6**2) ** 0.5)
