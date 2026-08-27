# Custom agents contract

## Goal

Carhibou must support its bundled Go agent and independent third-party agents through one
documented protocol. Adding a maintained implementation should normally require one
top-level directory containing `agent.toml`; backend code is reserved for setup that cannot
be expressed as static steps.

## Identity and compatibility

- `implementation_id` identifies an implementation, for example `carhibou.go` or
  `custom`.
- `agent_version` is the implementation's own SemVer and is informational. It must never be
  compared with the Carhibou server version.
- `protocol_version` is a positive integer. The server currently supports version `1` and
  rejects another version before consuming an enrollment token.
- Enrollment tokens are bound to one `implementation_id`. A token minted for one
  implementation cannot enroll another.
- Devices persist all three values. Human API responses expose them and provide a computed
  compatibility state.

## Manifest catalog

Every top-level implementation directory may contain `agent.toml` with schema version `1`.
The manifest declares:

- stable implementation id and display name;
- supported hardware summary;
- protocol version;
- whether setup is one command or guided;
- optional docs URL;
- ordered setup steps of kind `command`, `value`, `link`, or `manual`.

Static step strings may substitute `{server}`, `{token}`, and `{protocol_version}`. Values
inserted into commands must be shell-quoted. Unknown keys, duplicate ids, unsupported schema
versions, malformed steps, and missing required fields fail closed.

The production image copies manifests independently of Python packaging. The bundled Go
agent has a manifest. The server also exposes a built-in `custom` implementation whose
guided setup returns the server URL, one-time token, protocol version, and protocol docs.

## Human API and access

- Any authenticated human may list agent implementations.
- A vehicle operator may request implementation-specific enrollment instructions for that
  vehicle.
- Existing vehicle access rules remain the only authorization source.
- Enrollment creation accepts `implementation_id`; omission is not supported because
  backward compatibility is out of scope.
- The one-time token response contains ordered setup steps, not a special-case install
  command field.

## Device protocol

- Device enrollment requires `token`, `implementation_id`, `protocol_version`,
  `agent_version`, `hostname`, and optional hardware facts.
- A mismatched implementation or protocol is rejected without consuming the token.
- Existing credential realm separation, telemetry/config endpoints, revocation, and
  credential rotation remain unchanged.

## Frontend

- Enrollment starts by choosing an implementation from the server catalog.
- The UI shows hardware and setup style before minting a token.
- Setup steps render with appropriate copy, link, command, or instruction affordances.
- The custom implementation explains that it is for independently developed agents and
  links to the concise protocol documentation.
- Agent rows show implementation, agent version, protocol version, and compatibility without
  conflating any of them with online state.

## Verification

- Manifest parser tests cover valid, malformed, duplicate, and unknown-schema manifests.
- Protocol tests cover bundled and custom enrollment, implementation mismatch, unsupported
  protocol, token non-consumption on rejected enrollment, replay, and realm separation.
- Access tests cover viewer, operator, stranger, and administrator behavior.
- Frontend tests cover implementation selection and every setup-step kind.
- Production image and wheel tests prove the catalog exists outside a source checkout.
