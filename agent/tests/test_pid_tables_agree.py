"""The Go service and the Python CLI decode standard OBD-II independently.

Two implementations of one table drift the moment somebody edits one of them,
and the drift is silent: each side is internally consistent and its own tests
pass. This reads the Go table out of its source and holds the two to each other.
"""

import re
from pathlib import Path

import pytest

from agent.vehicle_agent.providers.standard_obd import PID_DECODERS

PROVIDERS = Path(__file__).parents[1] / "internal" / "providers"
GO_TABLE = PROVIDERS / "obd.go"
# An entry is one line: a PID, then a name that is either quoted or a constant,
# then the unit. The decoder itself is deliberately not compared - the two are
# written in different languages and only their published contract has to match.
ENTRY = re.compile(r'^\s*(0x[0-9A-Fa-f]+):\s*\{\s*(?:"([^"]*)"|([A-Za-z_]\w*))\s*,\s*"([^"]*)"')
CONSTANT = re.compile(r'^const\s+([A-Za-z_]\w*)\s*=\s*"([^"]*)"', re.MULTILINE)


def go_constants() -> dict[str, str]:
    constants: dict[str, str] = {}
    for source in PROVIDERS.glob("*.go"):
        constants.update(CONSTANT.findall(source.read_text(encoding="utf-8")))
    return constants


def go_table() -> dict[int, tuple[str, str]]:
    source = GO_TABLE.read_text(encoding="utf-8")
    start = source.index("var StandardPIDs = map[int]PIDDefinition{")
    block = source[start : source.index("\n}", start)]
    constants = go_constants()

    table: dict[int, tuple[str, str]] = {}
    for line in block.splitlines()[1:]:
        matched = ENTRY.match(line)
        if not matched:
            # Comments and blank lines are expected; anything else means the
            # table changed shape and this guard can no longer read it.
            stripped = line.strip()
            assert not stripped or stripped.startswith("//"), (
                f"unparsable StandardPIDs entry, so the tables are no longer pinned: {line!r}"
            )
            continue
        pid, quoted, identifier, unit = matched.groups()
        if quoted is not None:
            name = str(quoted)
        else:
            identifier = str(identifier)
            assert identifier in constants, (
                f"PID {pid} publishes constant {identifier}, which this guard cannot resolve"
            )
            name = constants[identifier]
        table[int(str(pid), 16)] = (name, str(unit))
    return table


def test_the_go_table_is_readable_at_all() -> None:
    """Without this the comparison below passes vacuously the day the Go table
    is reformatted: an empty parse would agree with nothing and complain about
    everything, or worse, agree with everything."""
    table = go_table()
    assert len(table) == len(PID_DECODERS), (
        f"parsed {len(table)} Go entries against {len(PID_DECODERS)} Python ones"
    )
    assert table[0x42] == ("battery.aux_voltage", "V"), (
        "the constant-named entry did not resolve, so the parse is not trustworthy"
    )


@pytest.mark.parametrize("pid", sorted(set(PID_DECODERS) | set(go_table())))
def test_both_agents_decode_the_same_pid_to_the_same_key_and_unit(pid: int) -> None:
    go = go_table().get(pid)
    python = PID_DECODERS.get(pid)
    assert go is not None, f"PID {pid:#04x} is decoded by the Python agent but not the Go service"
    assert python is not None, (
        f"PID {pid:#04x} is decoded by the Go service but not the Python agent"
    )
    key, unit = python[0], python[2]
    assert go == (key, unit), (
        f"PID {pid:#04x} disagrees: Go publishes {go[0]!r} in {go[1]!r}, "
        f"Python publishes {key!r} in {unit!r}"
    )
