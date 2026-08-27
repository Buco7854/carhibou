# Agents and enrollment

Enrollment starts by choosing an agent implementation from the server catalog. Review its
hardware summary and whether setup is one command or a guided sequence before creating a
token. Then name the agent and select its sampling cadence. The one-time token becomes a
permanent random device credential stored mode `0600`; it can authenticate only device
routes.

![Enrolled agents with their cadence](/screens/agents.png)

Each agent has separate driving and parked rates because most vehicles spend most of the
month parked. The agent reports its decision as `vehicle_in_use`, with
`activity_source` naming the evidence.

| Preset | Driving | Parked | Six signals, driven 1 h/day |
| --- | --- | --- | --- |
| Live | 1 s | 30 s | 256 MB/month |
| Standard | 5 s | 5 min | 40 MB/month |
| Saver | 15 s | 10 min | 15 MB/month |
| Frugal | 45 s | 15 min | 7 MB/month |
| Minimal | 3 min | 1 h | 2 MB/month |

Presets upload each reading as soon as it is sampled. Lowering sample resolution saves
more data without making the dashboard stale. A longer upload interval can batch samples
and reduce request overhead, but delays their visibility; most savings disappear beyond
about 30 seconds. Estimates use the selected signal count and expected driving hours.

## How parked state is decided

The agent tries evidence in this order, allowing any source to be absent:

1. A profile's `vehicle.ready` or `charging.active`. An explicit false readiness wins;
   charging counts as in use.
2. Whether the vehicle bus answered the latest read. This helps vehicles without a
   profile, even when decoded values have not changed.
3. Decoded or GPS speed above 3 km/h.
4. Displacement above 60 m when the receiver reports no speed.

Driving cadence remains active for three minutes after the last evidence, avoiding a
slowdown at brief stops. A newly started agent begins parked.

**Settings** changes cadence and creates a new configuration version. Apply it without
waiting for the next five-minute sync:

```sh
sudo carhibou-agent config --pull
sudo systemctl restart carhibou-agent
```

Revoke lost hardware immediately. Credential rotation invalidates the old credential and
returns its replacement once; copy it during that operation. Re-enrollment always uses a
new single-use token. See [agent installation and configuration](/agent/agent) for host
setup and hardware selection.

## Custom agents

Setup instructions are an ordered sequence. Each step has one of four forms:

- **Command** is ready to paste into a shell. Carhibou safely quotes substituted values.
- **Value** presents a value to copy into an application or device.
- **Link** opens implementation documentation or a browser-based setup tool.
- **Manual** explains an action that cannot be automated.

Choose the built-in `custom` implementation for an independently developed agent. Its
guided setup provides the server URL, one-time token, protocol version and protocol
documentation separately so the implementation can store each value safely. A custom agent
uses the same enrollment, configuration and telemetry endpoints as the bundled Go agent.

An enrollment is bound to the implementation selected when it was created. The server also
checks the protocol version before consuming the token, so a failed compatibility check can
be corrected without creating another enrollment.

Maintained implementations can be added to Carhibou with an `agent.toml` manifest describing
their name, hardware and setup steps. See [the agent protocol](/developers/architecture#agent-protocol)
for the implementation contract.

Each device row reports four compatibility facts independently: implementation, agent
version, protocol version and computed compatibility. Online state is separate and reports
only whether the server has heard from the device recently. An offline compatible agent and
an online incompatible record describe different conditions.
