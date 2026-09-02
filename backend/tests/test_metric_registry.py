from fastapi.testclient import TestClient

from backend.app.telemetry.registry import CANONICAL_METRICS, POSITION_FIELDS
from backend.app.telemetry.schemas import Position

REGISTRY = "/api/v1/metrics/registry"


def test_registry_is_readable_only_by_an_authenticated_user(client: TestClient) -> None:
    assert client.get(REGISTRY).status_code == 401


def test_registry_publishes_every_canonical_metric_in_the_agreed_shape(
    registered: tuple[TestClient, str],
) -> None:
    client, _csrf = registered
    response = client.get(REGISTRY)
    assert response.status_code == 200, response.text
    metrics = response.json()["metrics"]

    # Every definition, and nothing invented alongside them.
    assert [metric["key"] for metric in metrics] == sorted(CANONICAL_METRICS)
    assert all(
        set(metric)
        == {
            "key",
            "unit",
            "meaning",
            "kind",
            "value_type",
            "retained",
            "freshness_seconds",
        }
        for metric in metrics
    )

    # The two renamed fields carry the registry's own values rather than a copy
    # that can drift: retain_stale becomes retained, and a timedelta becomes
    # whole seconds.
    for metric in metrics:
        definition = CANONICAL_METRICS[metric["key"]]
        assert metric["retained"] is definition.retain_stale
        assert metric["freshness_seconds"] == int(definition.freshness.total_seconds())
        assert metric["unit"] == definition.unit
        assert metric["meaning"] == definition.meaning
        assert metric["kind"] == definition.kind
        assert metric["value_type"] == definition.value_type

    soc = next(metric for metric in metrics if metric["key"] == "battery.soc")
    assert soc == {
        "key": "battery.soc",
        "unit": "%",
        "meaning": "traction-battery state of charge from zero to one hundred",
        "kind": "state",
        "value_type": "number",
        "retained": True,
        "freshness_seconds": 900,
    }


def test_registry_describes_metrics_only(registered: tuple[TestClient, str]) -> None:
    """Position is one atomic observation with its own provenance, not a metric
    the registry defines, so it must not appear here."""
    client, _csrf = registered
    keys = [metric["key"] for metric in client.get(REGISTRY).json()["metrics"]]
    assert "position" not in keys
    assert not any(key.startswith("position.") for key in keys)


def test_position_descriptor_matches_the_wire_model_exactly(
    registered: tuple[TestClient, str],
) -> None:
    """The descriptor is what the interface renders, so a field the fix carries
    and the descriptor omits is a field nobody can see, and one the descriptor
    invents is a column that is always empty."""
    client, _csrf = registered
    position = client.get(REGISTRY).json()["position"]

    described = [field["key"] for field in position["fields"]]
    assert described == [field.key for field in POSITION_FIELDS]
    # Both directions, excluding none: the descriptor and the fix agree on the
    # whole set, not merely overlap.
    assert set(described) == set(Position.model_fields)

    assert all(set(field) == {"key", "unit", "meaning"} for field in position["fields"])
    assert all(field["unit"] and field["meaning"] for field in position["fields"])
    assert "indivisible observation" in position["meaning"]

    speed = next(field for field in position["fields"] if field["key"] == "speed")
    assert speed["unit"] == "km/h"
    assert speed["meaning"] == "GNSS ground speed; a candidate for vehicle.speed"


def test_position_fields_are_not_offered_as_metrics(
    registered: tuple[TestClient, str],
) -> None:
    """A fix is one observation. Its fields must not appear where a metric key is
    expected, or a hook author will reach for a latitude that does not exist."""
    client, _csrf = registered
    payload = client.get(REGISTRY).json()
    keys = {metric["key"] for metric in payload["metrics"]}
    assert keys.isdisjoint({field["key"] for field in payload["position"]["fields"]})
    assert keys == set(CANONICAL_METRICS)
