"""Import all models so Alembic and relationship resolution see one metadata graph."""

from backend.app.auth.models import AuthenticationIdentity, BrowserSession
from backend.app.dashboards.models import Dashboard
from backend.app.devices.models import Device, EnrollmentToken
from backend.app.hooks.models import Hook, HookExecution, HookRevision, HookState, Trigger
from backend.app.jobs.models import Job, WorkerHeartbeat
from backend.app.secrets.models import Secret
from backend.app.telemetry.models import Telemetry
from backend.app.users.models import User
from backend.app.vehicle_profiles.models import VehicleProfile
from backend.app.vehicle_state.models import VehicleState
from backend.app.vehicles.models import Vehicle, VehiclePhoto

__all__ = [
    "AuthenticationIdentity",
    "BrowserSession",
    "Dashboard",
    "Device",
    "EnrollmentToken",
    "Hook",
    "HookExecution",
    "HookRevision",
    "HookState",
    "Job",
    "Secret",
    "Telemetry",
    "Trigger",
    "User",
    "Vehicle",
    "VehicleProfile",
    "VehiclePhoto",
    "VehicleState",
    "WorkerHeartbeat",
]
