import json

from backend.app.connectors.mappings.teslamate import TESLAMATE_TOPICS, map_message


def test_all_teslamate_topics_have_an_exact_mapping() -> None:
    assert len(TESLAMATE_TOPICS) == 78
    assert len(set(TESLAMATE_TOPICS)) == 78
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
        mapped = map_message(topic, payloads[topic])
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


def test_teslamate_coercion_is_per_value_and_fail_open() -> None:
    assert map_message("new_topic", "  true ").metrics == {"teslamate.new_topic": True}
    assert map_message("new_topic", "12.5").metrics == {"teslamate.new_topic": 12.5}
    assert map_message("new_topic", "changed type").metrics == {
        "teslamate.new_topic": "changed type"
    }
    assert map_message("new_topic", "nil").metrics == {}
    assert map_message("new_topic", "").metrics == {}
    assert map_message("battery_level", "not numeric").metrics == {}
    assert map_message("battery_level", "not numeric").errors
    assert map_message("charging_state", "Complete").metrics == {"charging.active": False}
    assert map_message("charging_state", "Starting").metrics == {"charging.active": False}
    assert map_message("charging_state", "surprise").errors
    assert map_message("heading", "360").errors
    assert map_message("speed", "-1").errors
    assert map_message("new topic", "1").errors
    assert map_message("location", "not json").errors
    assert map_message("location", '{"latitude": 1}').errors
    flattened = map_message("future_json", '{"one":1,"two":false,"deep":{"no":1}}')
    assert flattened.metrics == {
        "teslamate.future_json.one": 1.0,
        "teslamate.future_json.two": False,
    }
