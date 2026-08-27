import json

import pytest
from pydantic import ValidationError

from backend.app.vehicle_profiles.mapping import MappingEngine
from backend.app.vehicle_profiles.schemas import (
    PROFILE_DEFINITION_ADAPTER,
    MappingProfileDefinition,
)
from backend.app.vehicle_profiles.services import built_in_definitions

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


def teslamate_engine() -> MappingEngine:
    definition = MappingProfileDefinition.model_validate(
        built_in_definitions()["teslamate-mqtt-v1"]
    )
    return MappingEngine(definition)


def mapping_definition(**changes: object) -> dict[str, object]:
    definition: dict[str, object] = {
        "id": "test-mapping",
        "name": "Test mapping",
        "version": 1,
        "description": "",
        "type": "mapping",
        "passthrough_prefix": "raw",
        "ignore": [],
        "rules": [],
    }
    definition.update(changes)
    return definition


def test_bundled_teslamate_profile_maps_all_78_topics_equivalently() -> None:
    assert len(TESLAMATE_TOPICS) == len(set(TESLAMATE_TOPICS)) == 78
    engine = teslamate_engine()
    deprecated = {
        "latitude",
        "longitude",
        "active_route_destination",
        "active_route_latitude",
        "active_route_longitude",
    }
    payloads = {topic: "sample" for topic in TESLAMATE_TOPICS}
    payloads.update(
        {
            "battery_level": "72",
            "power": "-4.5",
            "odometer": "12345.6",
            "charger_power": "7",
            "est_battery_range_km": "320.5",
            "charge_limit_soc": "80",
            "tpms_pressure_fl": "2.8",
            "tpms_pressure_fr": "2.9",
            "tpms_pressure_rl": "3.0",
            "tpms_pressure_rr": "3.1",
            "state": "online",
            "charging_state": "Charging",
            "location": json.dumps({"latitude": 48.1, "longitude": 2.2}),
            "elevation": "125",
            "heading": "182.5",
            "speed": "91",
            "active_route": json.dumps(
                {
                    "destination": "Home",
                    "minutes_to_arrival": 12,
                    "nested": {"ignored": True},
                    "empty": None,
                }
            ),
        }
    )

    metrics: dict[str, object] = {}
    position: dict[str, float] = {}
    for topic in TESLAMATE_TOPICS:
        mapped = engine.map(topic, payloads[topic])
        assert not mapped.errors, (topic, mapped.errors)
        metrics.update(mapped.metrics)
        position.update(mapped.position)

    assert position == {
        "latitude": 48.1,
        "longitude": 2.2,
        "altitude": 125.0,
        "heading": 182.5,
        "speed": 91.0,
    }
    assert metrics["battery.soc"] == 72.0
    assert metrics["battery.power"] == -4.5
    assert metrics["vehicle.odometer"] == 12345.6
    assert metrics["charging.power"] == 7.0
    assert metrics["vehicle.range"] == 320.5
    assert metrics["vehicle.state"] == "online"
    assert metrics["charging.active"] is True
    assert metrics["tyre.front_left_pressure"] == 2.8
    assert metrics["tyre.front_right_pressure"] == 2.9
    assert metrics["tyre.rear_left_pressure"] == 3.0
    assert metrics["tyre.rear_right_pressure"] == 3.1
    assert metrics["teslamate.charge_limit_soc"] == 80.0
    assert metrics["teslamate.tpms_soft_warning_fl"] == "sample"
    assert metrics["teslamate.active_route.destination"] == "Home"
    assert metrics["teslamate.active_route.minutes_to_arrival"] == 12.0
    assert "teslamate.active_route.nested" not in metrics
    assert not any(key.removeprefix("teslamate.") in deprecated for key in metrics)

    canonical_sources = {
        "battery_level",
        "power",
        "odometer",
        "charger_power",
        "est_battery_range_km",
        "tpms_pressure_fl",
        "tpms_pressure_fr",
        "tpms_pressure_rl",
        "tpms_pressure_rr",
        "state",
        "charging_state",
        "location",
        "elevation",
        "heading",
        "speed",
        "active_route",
    }
    passthrough = set(TESLAMATE_TOPICS) - deprecated - canonical_sources
    assert all(f"teslamate.{topic}" in metrics for topic in passthrough)
    assert set(metrics) == {
        *(f"teslamate.{topic}" for topic in passthrough),
        "battery.soc",
        "battery.power",
        "vehicle.odometer",
        "charging.power",
        "vehicle.range",
        "vehicle.state",
        "charging.active",
        "tyre.front_left_pressure",
        "tyre.front_right_pressure",
        "tyre.rear_left_pressure",
        "tyre.rear_right_pressure",
        "teslamate.active_route.destination",
        "teslamate.active_route.minutes_to_arrival",
    }


def test_mapping_engine_supports_every_transform() -> None:
    engine = MappingEngine(
        mapping_definition(
            passthrough_prefix="",
            rules=[
                {
                    "match": "scaled",
                    "target": "metric.scaled",
                    "transform": {"scale": 2, "offset": 3},
                },
                {
                    "match": "state",
                    "target": "metric.state",
                    "transform": {"enum": {"ready": "driving", "*": "parked"}},
                },
                {
                    "match": "switch",
                    "target": "metric.switch",
                    "transform": {"boolean": True},
                },
                {
                    "match": "object",
                    "target": "metric.object",
                    "transform": {"json": True},
                },
                {
                    "match": "location",
                    "target": "position",
                    "transform": {"json": True},
                },
            ],
        )
    )
    assert engine.map("scaled", "4").metrics == {"metric.scaled": 11.0}
    assert engine.map("state", "ready").metrics == {"metric.state": "driving"}
    assert engine.map("state", "unknown").metrics == {"metric.state": "parked"}
    assert engine.map("switch", "YES").metrics == {"metric.switch": True}
    assert engine.map("switch", "off").metrics == {"metric.switch": False}
    assert engine.map("object", '{"one":1,"two":false,"deep":{"no":1}}').metrics == {
        "metric.object.one": 1.0,
        "metric.object.two": False,
    }
    assert engine.map("location", '{"latitude":48.1,"longitude":2.2}').position == {
        "latitude": 48.1,
        "longitude": 2.2,
    }
    assert engine.map("unmatched", "42").metrics == {}


def test_mapping_runtime_coercion_is_per_value_and_fail_open() -> None:
    engine = teslamate_engine()
    assert engine.map("new_topic", "  true ").metrics == {"teslamate.new_topic": True}
    assert engine.map("new_topic", "12.5").metrics == {"teslamate.new_topic": 12.5}
    assert engine.map("new_topic", "changed type").metrics == {
        "teslamate.new_topic": "changed type"
    }
    assert engine.map("state", "1").metrics == {"vehicle.state": "1"}
    assert engine.map("state", "true").metrics == {"vehicle.state": "true"}
    assert engine.map("charging_state", "charging").metrics == {"charging.active": True}
    assert engine.map("new_topic", "nil").metrics == {}
    assert engine.map("battery_level", "not numeric").metrics == {}
    assert engine.map("battery_level", "not numeric").errors
    assert engine.map("charging_state", "surprise").metrics == {"charging.active": False}
    assert engine.map("heading", "360").errors
    assert engine.map("speed", "-1").errors
    assert engine.map("new topic", "1").errors
    assert engine.map("location", "not json").errors
    assert engine.map("location", '{"latitude":1}').errors
    empty_location = engine.map("location", '{"label":"nowhere"}')
    assert not empty_location.metrics and not empty_location.position
    assert empty_location.errors == ["location: position object has no supported fields"]
    assert engine.map("future_json", "{bad json").errors
    assert engine.map("new_topic", b"\xff").errors


@pytest.mark.parametrize(
    "change",
    [
        {"unknown": True},
        {"rules": [{"match": "one", "target": "metric.one", "transform": {"boolean": False}}]},
        {"rules": [{"match": "one", "target": "metric.one", "transform": {"json": False}}]},
        {"rules": [{"match": "one", "target": "bad target"}]},
        {
            "rules": [
                {"match": "one", "target": "metric.one"},
                {"match": "one", "target": "metric.two"},
            ]
        },
        {
            "rules": [
                {
                    "match": "one",
                    "target": "metric.one",
                    "transform": {"enum": {"one": 1}, "boolean": True},
                }
            ]
        },
        {"ignore": ["one"], "rules": [{"match": "one", "target": "metric.one"}]},
    ],
)
def test_mapping_profile_validation_fails_closed(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PROFILE_DEFINITION_ADAPTER.validate_python(mapping_definition(**change))
