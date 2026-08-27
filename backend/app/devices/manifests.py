"""Strict discovery of top-level agent implementation manifests."""

import re
import string
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit

MANIFEST_NAME = "agent.toml"
MANIFEST_SCHEMA = 1
DISTRIBUTION_ROOT = Path(__file__).resolve().parents[3]
IMAGE_MANIFEST_DIR = Path("/app/agent-manifests")
IMPLEMENTATION_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
TEMPLATE_FIELDS = {"server", "token", "protocol_version"}

SetupKind = Literal["command", "guided"]
StepKind = Literal["command", "value", "link", "manual"]


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class ManifestStep:
    kind: StepKind
    text: str = ""
    command: str = ""
    value: str = ""
    url: str = ""


@dataclass(frozen=True)
class AgentManifest:
    id: str
    name: str
    hardware: str
    protocol_version: int
    setup_kind: SetupKind
    docs_url: str
    directory: Path
    setup_steps: tuple[ManifestStep, ...]


def _table(
    value: object,
    *,
    source: Path,
    label: str,
    required: set[str],
    allowed: set[str],
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ManifestError(f"{source}: {label} must be a table")
    table = cast(dict[str, object], value)
    unknown = set(table) - allowed
    if unknown:
        raise ManifestError(f"{source}: {label} has unknown key {sorted(unknown)[0]!r}")
    missing = required - set(table)
    if missing:
        raise ManifestError(f"{source}: {label} is missing {sorted(missing)[0]!r}")
    return table


def _nonempty_string(table: dict[str, object], key: str, source: Path) -> str:
    value = table[key]
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{source}: {key!r} must be a non-empty string")
    return value


def _validate_template(value: str, source: Path, field: str) -> None:
    try:
        parsed = string.Formatter().parse(value)
        for _literal, name, format_spec, conversion in parsed:
            if name is None:
                continue
            if name not in TEMPLATE_FIELDS or format_spec or conversion:
                raise ManifestError(
                    f"{source}: {field!r} may substitute only "
                    "{server}, {token}, and {protocol_version}"
                )
    except ValueError as exc:
        raise ManifestError(f"{source}: {field!r} contains a malformed template") from exc


def _parse_step(raw: object, source: Path) -> ManifestStep:
    step = _table(
        raw,
        source=source,
        label="setup step",
        required={"kind"},
        allowed={"kind", "text", "command", "value", "url"},
    )
    kind = _nonempty_string(step, "kind", source)
    if kind not in {"command", "value", "link", "manual"}:
        raise ManifestError(f"{source}: unsupported setup step kind {kind!r}")
    strings: dict[str, str] = {}
    for field in ("text", "command", "value", "url"):
        value = step.get(field, "")
        if not isinstance(value, str):
            raise ManifestError(f"{source}: setup step {field!r} must be a string")
        _validate_template(value, source, field)
        strings[field] = value

    payloads = {field for field in ("command", "value", "url") if strings[field]}
    expected = {
        "command": {"command"},
        "value": {"value"},
        "link": {"url"},
        "manual": set(),
    }[kind]
    if payloads != expected:
        raise ManifestError(
            f"{source}: {kind!r} step must carry exactly {sorted(expected) or 'no payload'}"
        )
    if kind == "manual" and not strings["text"].strip():
        raise ManifestError(f"{source}: manual setup step must contain text")
    return ManifestStep(kind=cast(StepKind, kind), **strings)


def _parse(source: Path) -> AgentManifest:
    try:
        document = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(f"{source}: unreadable agent manifest ({exc})") from exc
    root = _table(
        document,
        source=source,
        label="manifest",
        required={"schema", "implementation"},
        allowed={"schema", "implementation", "setup"},
    )
    schema = root["schema"]
    if type(schema) is not int or schema != MANIFEST_SCHEMA:
        raise ManifestError(f"{source}: unsupported manifest schema {schema!r}")

    implementation = _table(
        root["implementation"],
        source=source,
        label="implementation",
        required={"id", "name", "hardware", "protocol_version", "setup_kind"},
        allowed={"id", "name", "hardware", "protocol_version", "setup_kind", "docs_url"},
    )
    identifier = _nonempty_string(implementation, "id", source)
    if len(identifier) > 100 or not IMPLEMENTATION_ID.fullmatch(identifier):
        raise ManifestError(f"{source}: implementation id is malformed")
    protocol_version = implementation["protocol_version"]
    if type(protocol_version) is not int or protocol_version < 1:
        raise ManifestError(f"{source}: protocol_version must be a positive integer")
    setup_kind = _nonempty_string(implementation, "setup_kind", source)
    if setup_kind not in {"command", "guided"}:
        raise ManifestError(f"{source}: setup_kind must be 'command' or 'guided'")
    docs_url = implementation.get("docs_url", "")
    if not isinstance(docs_url, str):
        raise ManifestError(f"{source}: docs_url must be a string")
    if docs_url:
        parsed_url = urlsplit(docs_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ManifestError(f"{source}: docs_url must be an HTTP(S) URL")

    raw_steps: object = []
    if "setup" in root:
        setup = _table(
            root["setup"],
            source=source,
            label="setup",
            required={"steps"},
            allowed={"steps"},
        )
        raw_steps = setup["steps"]
    if not isinstance(raw_steps, list):
        raise ManifestError(f"{source}: setup.steps must be a list")

    return AgentManifest(
        id=identifier,
        name=_nonempty_string(implementation, "name", source),
        hardware=_nonempty_string(implementation, "hardware", source),
        protocol_version=protocol_version,
        setup_kind=cast(SetupKind, setup_kind),
        docs_url=docs_url,
        directory=source.parent,
        setup_steps=tuple(_parse_step(raw, source) for raw in raw_steps),
    )


def discover_manifests(root: Path) -> tuple[AgentManifest, ...]:
    manifests = tuple(_parse(source) for source in sorted(root.glob(f"*/{MANIFEST_NAME}")))
    identifiers = [manifest.id for manifest in manifests]
    if len(identifiers) != len(set(identifiers)):
        raise ManifestError(f"{root}: duplicate implementation id")
    return manifests


def _definition(manifest: AgentManifest) -> tuple[object, ...]:
    return (
        manifest.id,
        manifest.name,
        manifest.hardware,
        manifest.protocol_version,
        manifest.setup_kind,
        manifest.docs_url,
        manifest.setup_steps,
    )


@lru_cache(maxsize=1)
def agent_manifests() -> tuple[AgentManifest, ...]:
    """Return manifests from a checkout, wheel, or image mirror.

    An image intentionally mirrors wheel manifests independently. Identical mirrors are
    collapsed, while two different definitions claiming one id fail closed.
    """

    found: dict[str, AgentManifest] = {}
    for root in (DISTRIBUTION_ROOT, IMAGE_MANIFEST_DIR):
        if not root.is_dir():
            continue
        for manifest in discover_manifests(root):
            existing = found.get(manifest.id)
            if existing and _definition(existing) != _definition(manifest):
                raise ManifestError(f"duplicate implementation id {manifest.id!r}")
            found.setdefault(manifest.id, manifest)
    return tuple(found.values())
