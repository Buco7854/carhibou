from pathlib import Path

import pytest

from backend.app.devices import manifests
from backend.app.devices.manifests import ManifestError, discover_manifests

MANIFEST = """
schema = 1

[implementation]
id = "community.example"
name = "Example agent"
hardware = "Linux board"
protocol_version = 1
setup_kind = "guided"
docs_url = "https://example.invalid/agent"

[[setup.steps]]
kind = "manual"
text = "Prepare the hardware"

[[setup.steps]]
kind = "command"
command = "example --server {server} --token {token} --protocol {protocol_version}"

[[setup.steps]]
kind = "value"
text = "Token"
value = "{token}"

[[setup.steps]]
kind = "link"
text = "Open setup"
url = "https://example.invalid/setup"
"""


def _write(root: Path, directory: str, document: str = MANIFEST) -> None:
    target = root / directory
    target.mkdir(parents=True)
    (target / "agent.toml").write_text(document)


def test_valid_manifest_preserves_order_and_protocol(tmp_path: Path) -> None:
    _write(tmp_path, "example-agent")

    manifest = discover_manifests(tmp_path)[0]

    assert manifest.id == "community.example"
    assert manifest.protocol_version == 1
    assert manifest.setup_kind == "guided"
    assert [step.kind for step in manifest.setup_steps] == [
        "manual",
        "command",
        "value",
        "link",
    ]


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        ("schema = 1", "schema = 2"),
        ("schema = 1", "schema = true"),
        ('id = "community.example"', 'id = "Invalid id"'),
        ('name = "Example agent"', "name = 4"),
        ("protocol_version = 1", "protocol_version = 0"),
        ("protocol_version = 1", "protocol_version = true"),
        ('setup_kind = "guided"', 'setup_kind = "automatic"'),
        ('kind = "manual"', 'kind = "manual"\nunknown = "closed"'),
        ('kind = "command"', 'kind = "command"\nvalue = "wrong payload"'),
        ('text = "Prepare the hardware"', 'text = ""'),
        ("{server}", "{server.hostname}"),
    ],
)
def test_malformed_manifest_fails_closed(tmp_path: Path, needle: str, replacement: str) -> None:
    _write(tmp_path, "bad-agent", MANIFEST.replace(needle, replacement, 1))

    with pytest.raises(ManifestError):
        discover_manifests(tmp_path)


@pytest.mark.parametrize(
    "document",
    [
        "this is not valid TOML = [",
        "[implementation]\nid = 'missing-schema'\n",
        MANIFEST.replace("schema = 1", "schema = 1\nunknown = true"),
        MANIFEST.replace(
            'id = "community.example"',
            'id = "community.example"\nunknown = true',
        ),
        MANIFEST.replace("[[setup.steps]]", "[setup]\nunknown = true\n[[setup.steps]]", 1),
        MANIFEST.replace('hardware = "Linux board"\n', ""),
    ],
)
def test_unknown_keys_and_missing_fields_fail_closed(tmp_path: Path, document: str) -> None:
    _write(tmp_path, "bad-agent", document)

    with pytest.raises(ManifestError):
        discover_manifests(tmp_path)


def test_duplicate_implementation_ids_fail_closed(tmp_path: Path) -> None:
    _write(tmp_path, "first")
    _write(tmp_path, "second")

    with pytest.raises(ManifestError):
        discover_manifests(tmp_path)


def test_image_mirror_accepts_only_an_identical_wheel_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "wheel"
    image = tmp_path / "image"
    _write(wheel, "agent")
    _write(image, "agent")
    monkeypatch.setattr(manifests, "DISTRIBUTION_ROOT", wheel)
    monkeypatch.setattr(manifests, "IMAGE_MANIFEST_DIR", image)
    manifests.agent_manifests.cache_clear()
    try:
        assert [entry.id for entry in manifests.agent_manifests()] == ["community.example"]
        (image / "agent" / "agent.toml").write_text(
            MANIFEST.replace("Example agent", "Conflicting agent")
        )
        manifests.agent_manifests.cache_clear()
        with pytest.raises(ManifestError):
            manifests.agent_manifests()
    finally:
        manifests.agent_manifests.cache_clear()


def test_bundled_manifest_is_available_from_the_installed_agent_package() -> None:
    bundled = Path(__file__).resolve().parents[2] / "agent" / "agent.toml"

    manifest = discover_manifests(bundled.parent.parent)[0]

    assert bundled.is_file()
    assert manifest.id == "carhibou.go"
    assert manifest.protocol_version == 1
