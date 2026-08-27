"""Agent protocol identities, catalog descriptions, and setup rendering."""

import shlex
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from backend.app.branding import APP_VERSION
from backend.app.common.settings import get_settings
from backend.app.devices.manifests import (
    AgentManifest,
    ManifestError,
    ManifestStep,
    SetupKind,
    StepKind,
    agent_manifests,
)

SUPPORTED_PROTOCOL_VERSION = 1
BUNDLED_IMPLEMENTATION_ID = "carhibou.go"
CUSTOM_IMPLEMENTATION_ID = "custom"
Compatibility = Literal["compatible", "incompatible"]


class DescribedImplementation(TypedDict):
    id: str
    name: str
    hardware: str
    protocol_version: int
    setup_kind: SetupKind
    docs_url: str


class RenderedStep(TypedDict):
    kind: StepKind
    text: str
    command: str
    value: str
    url: str


@dataclass(frozen=True)
class SetupStep:
    kind: StepKind
    text: str = ""
    command: str = ""
    value: str = ""
    url: str = ""


CUSTOM_IMPLEMENTATION = AgentManifest(
    id=CUSTOM_IMPLEMENTATION_ID,
    name="Custom agent",
    hardware="Any hardware supported by your implementation",
    protocol_version=SUPPORTED_PROTOCOL_VERSION,
    setup_kind="guided",
    docs_url="",
    directory=Path("<built-in>"),
    setup_steps=(
        ManifestStep(kind="value", text="Server URL", value="{server}"),
        ManifestStep(kind="value", text="Enrollment token", value="{token}"),
        ManifestStep(kind="value", text="Protocol version", value="{protocol_version}"),
        ManifestStep(kind="link", text="Protocol documentation", url="{server}/api/docs"),
    ),
)


def compatibility(protocol_version: int) -> Compatibility:
    return "compatible" if protocol_version == SUPPORTED_PROTOCOL_VERSION else "incompatible"


def registered_implementations() -> tuple[AgentManifest, ...]:
    manifests = agent_manifests()
    if any(manifest.id == CUSTOM_IMPLEMENTATION_ID for manifest in manifests):
        raise ManifestError(f"implementation id {CUSTOM_IMPLEMENTATION_ID!r} is reserved")
    return (*manifests, CUSTOM_IMPLEMENTATION)


def implementation_by_id(implementation_id: str) -> AgentManifest | None:
    return next(
        (
            implementation
            for implementation in registered_implementations()
            if implementation.id == implementation_id
        ),
        None,
    )


def _bundled_setup(_manifest: AgentManifest, token: str) -> tuple[SetupStep, ...]:
    base = get_settings().public_url.rstrip("/")
    insecure = " --allow-insecure-http" if base.startswith("http://") else ""
    command = (
        f"curl -fsSL {shlex.quote(f'{base}/install-agent')} | sudo sh -s -- "
        f"--server {shlex.quote(base)} --token {shlex.quote(token)} "
        f"--version {shlex.quote(APP_VERSION)}{insecure}"
    )
    return (SetupStep(kind="command", command=command),)


SETUP_BUILDERS: dict[str, Callable[[AgentManifest, str], tuple[SetupStep, ...]]] = {
    BUNDLED_IMPLEMENTATION_ID: _bundled_setup
}


def _static_setup(manifest: AgentManifest, token: str) -> tuple[SetupStep, ...]:
    base = get_settings().public_url.rstrip("/")
    plain = {
        "server": base,
        "token": token,
        "protocol_version": str(manifest.protocol_version),
    }
    quoted = {key: shlex.quote(value) for key, value in plain.items()}
    rendered = []
    for step in manifest.setup_steps:
        values = quoted if step.kind == "command" else plain
        rendered.append(
            SetupStep(
                kind=step.kind,
                text=step.text.format(**plain),
                command=step.command.format(**values),
                value=step.value.format(**plain),
                url=step.url.format(**plain),
            )
        )
    return tuple(rendered)


def setup_steps(manifest: AgentManifest, token: str) -> tuple[SetupStep, ...]:
    builder = SETUP_BUILDERS.get(manifest.id)
    if builder:
        return builder(manifest, token)
    if not manifest.setup_steps:
        raise ManifestError(f"{manifest.id}: declare setup steps or register a setup builder")
    return _static_setup(manifest, token)


def describe(manifest: AgentManifest) -> DescribedImplementation:
    return {
        "id": manifest.id,
        "name": manifest.name,
        "hardware": manifest.hardware,
        "protocol_version": manifest.protocol_version,
        "setup_kind": manifest.setup_kind,
        "docs_url": manifest.docs_url,
    }


def render_steps(manifest: AgentManifest, token: str) -> list[RenderedStep]:
    return [
        {
            "kind": step.kind,
            "text": step.text,
            "command": step.command,
            "value": step.value,
            "url": step.url,
        }
        for step in setup_steps(manifest, token)
    ]
