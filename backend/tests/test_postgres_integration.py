import os
from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.common.database import get_db
from backend.app.jobs.models import Job
from backend.app.jobs.services import claim_job
from backend.app.main import app
from backend.app.telemetry.models import Telemetry
from backend.app.vehicle_state.models import VehicleState

pytestmark = pytest.mark.postgres
DATABASE_URL = os.getenv("VEHINODE_TEST_DATABASE_URL")


@pytest.fixture
def postgres_factory() -> Generator[sessionmaker[Session], None, None]:
    if not DATABASE_URL:
        pytest.skip("VEHINODE_TEST_DATABASE_URL is not configured")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE users CASCADE"))
        data_type = connection.scalar(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='telemetry' AND column_name='metrics'"
            )
        )
        assert data_type == "jsonb"
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE users CASCADE"))
        connection.execute(text("TRUNCATE TABLE jobs, worker_heartbeats CASCADE"))
    engine.dispose()


@pytest.fixture
def postgres_client(
    postgres_factory: sessionmaker[Session],
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        with postgres_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_postgres_idempotency_state_and_skip_locked(
    postgres_client: TestClient, postgres_factory: sessionmaker[Session]
) -> None:
    registration = postgres_client.post(
        "/api/v1/auth/register",
        json={
            "email": "postgres@example.com",
            "password": "postgres-integration-password",
            "display_name": "Postgres",
        },
    )
    csrf = registration.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    vehicle = postgres_client.post(
        "/api/v1/vehicles", headers=headers, json={"name": "PostgreSQL vehicle"}
    ).json()
    enrollment = postgres_client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers=headers,
        json={"name": "Database agent"},
    ).json()
    enrolled = postgres_client.post(
        "/api/v1/device/enroll",
        json={"token": enrollment["token"], "agent_version": "test", "hostname": "pg"},
    ).json()
    sample_id = str(uuid4())
    batch = {
        "boot_id": str(uuid4()),
        "samples": [
            {
                "id": sample_id,
                "sequence": 1,
                "recorded_at": datetime.now(UTC).isoformat(),
                "position": {"latitude": 48.0, "longitude": 2.0},
                "metrics": {"battery.soc": 73},
            }
        ],
    }
    device_headers = {"Authorization": f"Device {enrolled['credential']}"}
    assert postgres_client.post(
        "/api/v1/device/telemetry/batch", headers=device_headers, json=batch
    ).json()["accepted"] == [sample_id]
    assert postgres_client.post(
        "/api/v1/device/telemetry/batch", headers=device_headers, json=batch
    ).json()["duplicates"] == [sample_id]
    with postgres_factory() as db:
        assert db.scalar(select(Telemetry).where(Telemetry.id == sample_id)) is not None
        assert db.get(VehicleState, vehicle["id"]).latest_metrics["battery.soc"] == 73  # type: ignore[union-attr]
        db.add_all([Job(type="test.one", payload={}), Job(type="test.two", payload={})])
        db.commit()

    first = postgres_factory()
    second = postgres_factory()
    try:
        first.begin()
        first_job = claim_job(first)
        assert first_job is not None
        first.flush()
        second.begin()
        second_job = claim_job(second)
        assert second_job is not None
        assert second_job.id != first_job.id
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()
