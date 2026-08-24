import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from agent.vehicle_agent.simulator.journey import SimulatedCZeroJourney
from backend.app.hooks.models import HookExecution, HookState
from backend.app.jobs.models import Job
from backend.app.worker import execute_hook_job


class Receiver(BaseHTTPRequestHandler):
    received: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        self.received.append(json.loads(self.rfile.read(length)))
        self.send_response(204)
        self.end_headers()

    def log_message(self, _format: str, *args: object) -> None:
        return


def test_complete_simulator_dashboard_and_hook_scenario(
    client: TestClient, db_factory: sessionmaker[Session]
) -> None:
    Receiver.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "journey@example.com",
                "password": "complete-e2e-test-password",
                "display_name": "Journey Owner",
            },
        )
        assert registration.status_code == 201
        csrf = registration.json()["csrf_token"]
        browser_headers = {"X-CSRF-Token": csrf}

        vehicle = client.post(
            "/api/v1/vehicles",
            headers=browser_headers,
            json={
                "name": "Simulated C-Zero",
                "manufacturer": "Citroën",
                "model": "C-Zero",
                "vehicle_profile": "citroen-c-zero-v1",
            },
        ).json()
        enrollment = client.post(
            f"/api/v1/vehicles/{vehicle['id']}/enrollments",
            headers=browser_headers,
            json={"name": "Journey simulator"},
        ).json()
        enrolled = client.post(
            "/api/v1/device/enroll",
            json={
                "token": enrollment["token"],
                "agent_version": "0.1.0",
                "hostname": "simulator",
                "hardware": {"model": "simulated-pi-zero"},
            },
        ).json()

        receiver_url = f"http://127.0.0.1:{server.server_port}/hook"
        hook = client.post(
            "/api/v1/hooks",
            headers=browser_headers,
            json={
                "name": "Journey receiver",
                "enabled": True,
                "vehicle_id": vehicle["id"],
                "source": (
                    'ctx.state["count"] = ctx.state.get("count", 0) + 1\n'
                    'ctx.state["last_timestamp"] = ctx.telemetry.recorded_at.isoformat()\n'
                    f'ctx.http.post("{receiver_url}", '
                    'json={"vehicle": ctx.vehicle.id, "soc": '
                    'ctx.telemetry.metrics["battery.soc"]})'
                ),
            },
        )
        assert hook.status_code == 201, hook.text

        journey = SimulatedCZeroJourney(20)
        boot_time = datetime.now(UTC) - timedelta(seconds=10)
        samples = [journey.sample(index, boot_time).as_payload() for index in range(3)]
        sent = client.post(
            "/api/v1/device/telemetry/batch",
            headers={"Authorization": f"Device {enrolled['credential']}"},
            json={"boot_id": str(uuid4()), "samples": samples},
        )
        assert sent.status_code == 200, sent.text
        assert len(sent.json()["accepted"]) == 3

        current = client.get(f"/api/v1/vehicles/{vehicle['id']}").json()
        last_metrics = cast(dict[str, object], samples[-1]["metrics"])
        last_position = cast(dict[str, object], samples[-1]["position"])
        assert current["state"]["metrics"]["battery.soc"] == last_metrics["battery.soc"]
        assert current["state"]["position"]["latitude"] == last_position["latitude"]
        history = client.get(f"/api/v1/vehicles/{vehicle['id']}/history").json()
        assert history["original_count"] == 3
        assert "battery.soc" in history["available_metrics"]

        layout = {
            "widgets": [
                {
                    "id": "soc-card",
                    "type": "battery-gauge",
                    "vehicle_id": vehicle["id"],
                    "metric": "battery.soc",
                    "x": 0,
                    "y": 0,
                    "w": 3,
                    "h": 3,
                }
            ]
        }
        dashboard = client.post(
            "/api/v1/dashboards",
            headers=browser_headers,
            json={"name": "Journey", "is_default": True, "layout": layout},
        )
        assert dashboard.status_code == 201
        saved_layout = client.get("/api/v1/dashboards").json()[0]["layout"]
        assert saved_layout["widgets"][0] == {**layout["widgets"][0], "settings": {}}

        with db_factory() as db:
            jobs = list(
                db.scalars(select(Job).where(Job.status == "pending").order_by(Job.created_at))
            )
            assert len(jobs) == 3
            for job in jobs:
                job.status = "running"
                db.commit()
                execute_hook_job(db, job)
                db.commit()

        executions = client.get(f"/api/v1/hooks/{hook.json()['id']}/executions").json()
        assert len(executions) == 3
        assert all(row["status"] == "success" for row in executions)
        with db_factory() as db:
            state = db.get(HookState, hook.json()["id"])
            assert state is not None
            assert state.value["count"] == 3
            assert db.scalar(select(HookExecution).where(HookExecution.status == "failed")) is None
        assert len(Receiver.received) == 3
        assert Receiver.received[-1]["vehicle"] == vehicle["id"]
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
