from fastapi.testclient import TestClient

from backend.app.telemetry.registry import CANONICAL_METRICS

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
