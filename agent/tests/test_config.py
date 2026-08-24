from pathlib import Path

import pytest

from agent.vehicle_agent.config import ConfigurationError, ConfigurationStore


def data(version: int, sample: int = 5) -> dict[str, object]:
    return {
        "version": version,
        "sampling": {"default_seconds": sample},
        "upload": {"default_seconds": 30},
        "vehicle_profile": "citroen-c-zero-v1",
    }


def test_invalid_remote_configuration_does_not_replace_last_known_good(
    tmp_path: Path,
) -> None:
    store = ConfigurationStore(tmp_path / "config.json")
    installed = store.install_if_newer(data(1))
    assert installed.version == 1
    before = (tmp_path / "config.json").read_text()

    with pytest.raises(ConfigurationError):
        store.install_if_newer(data(2, sample=0))
    assert (tmp_path / "config.json").read_text() == before
    assert store.load().version == 1


def test_configuration_version_cannot_roll_back(tmp_path: Path) -> None:
    store = ConfigurationStore(tmp_path / "config.json")
    store.install_if_newer(data(3))
    with pytest.raises(ConfigurationError, match="rollback"):
        store.install_if_newer(data(2))


def test_same_configuration_version_does_not_rewrite_sd_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConfigurationStore(tmp_path / "config.json")
    store.install_if_newer(data(3))

    def unexpected_write(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("same-version configuration should not be rewritten")

    monkeypatch.setattr("agent.vehicle_agent.config.NamedTemporaryFile", unexpected_write)
    assert store.install_if_newer(data(3)).version == 3


def test_inline_owner_profile_is_validated_and_kept_as_last_known_good(tmp_path: Path) -> None:
    profile = {
        "id": "owner-profile-1",
        "name": "Owner profile",
        "version": 1,
        "signals": [
            {
                "name": "battery.soc",
                "source": {"type": "can", "can_id": 0x374},
                "decoder": {"byte_offset": 0, "data_type": "uint8", "scale": 0.5},
                "status": "experimental",
            }
        ],
    }
    remote = data(1)
    remote["vehicle_profile"] = "owner-profile-1"
    remote["vehicle_profile_definition"] = profile
    store = ConfigurationStore(tmp_path / "config.json")

    installed = store.install_if_newer(remote)

    assert installed.vehicle_profile_definition == profile
    assert store.load().vehicle_profile_definition == profile


def test_inline_profile_must_match_reference_and_decoder_contract(tmp_path: Path) -> None:
    remote = data(1)
    remote["vehicle_profile_definition"] = {"id": "another-profile", "signals": []}
    store = ConfigurationStore(tmp_path / "config.json")
    with pytest.raises(ConfigurationError, match="does not match"):
        store.install_if_newer(remote)
