from pathlib import Path

import pytest

from agent.vehicle_agent.capture import CANRecorder, replay_capture
from agent.vehicle_agent.models import CANFrame
from agent.vehicle_agent.profile_decoder import VehicleProfileDecoder
from agent.vehicle_agent.providers.obdlink import AdapterError, parse_can_frame
from agent.vehicle_agent.providers.standard_obd import (
    decode_standard_pid,
    parse_dtc_response,
    parse_obd_response,
    parse_vin_response,
)


def profile_path() -> Path:
    return Path(__file__).parents[1] / "profiles" / "citroen-c-zero-v1.yaml"


def test_can_frame_parsing_capture_and_replay(tmp_path: Path) -> None:
    frame = parse_can_frame("374 8 96 00 00 00 00 00 00 00", timestamp=12.5)
    assert frame.can_id == 0x374
    assert frame.data[0] == 0x96
    with pytest.raises(AdapterError):
        parse_can_frame("374 8 01 02")

    capture = tmp_path / "capture.jsonl"
    with capture.open("w") as output:
        recorder = CANRecorder(output, {"profile": "citroen-c-zero-v1"})
        recorder.write(frame)
    replayed = list(replay_capture(capture))
    assert replayed[0][0]["profile"] == "citroen-c-zero-v1"
    assert replayed[0][1] == frame


def test_experimental_c_zero_profile_decodes_documented_starting_points() -> None:
    decoder = VehicleProfileDecoder.from_path(profile_path())
    # Byte 1 carries the charge; byte 0 is something else. Taken from a script
    # proven against a physical C-Zero.
    soc = decoder.decode(CANFrame(1, 0x374, bytes.fromhex("0096000000000000")))
    assert {value.name: value.value for value in soc}["battery.soc"] == 70
    assert {value.name: value.unit for value in soc}["battery.soc"] == "%"

    battery = decoder.decode(CANFrame(2, 0x373, bytes.fromhex("000080640CE40000")))
    values = {value.name: value.value for value in battery}
    # (0x8064 - 0x8000) / 100 = +1.0 A, the direction the proven script reports.
    assert values["battery.current"] == pytest.approx(1.0)
    assert values["battery.pack_voltage"] == pytest.approx(330.0)

    # 0x101 is transmitted only while the car is awake, and says which way.
    state = decoder.decode(CANFrame(3, 0x101, bytes.fromhex("04")))
    assert {value.name: value.value for value in state}["vehicle.state"] == "ready"


def test_standard_obd_parsing() -> None:
    payload = parse_obd_response(1, 0x0C, ["7E8 04 41 0C 1A F8"])
    assert payload == bytes.fromhex("1AF8")
    assert decode_standard_pid(0x0C, payload or b"") == ("engine.rpm", 1726.0, "rpm")


def test_standard_obd_vin_and_dtc_parsing() -> None:
    vin = parse_vin_response(
        [
            "7E8 10 14 49 02 01 56 46 33",
            "7E8 21 31 58 58 58 58 58 58",
            "7E8 22 58 58 58 58 58 58 58",
        ]
    )
    assert vin == "VF31XXXXXXXXXXXXX"
    assert parse_dtc_response(["7E8 06 43 01 33 C1 23 00"]) == ["P0133", "U0123"]
