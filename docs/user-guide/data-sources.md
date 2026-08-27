# Data sources

Carhibou accepts telemetry from enrolled agents and hosted connectors. Agents push data
from vehicle hardware. Connectors receive data from an external service and feed it into
the same state, history and hook pipeline.

## Agents and enrollment

Enrollment starts by choosing an agent implementation from the server catalog. Review its
hardware summary and whether setup is one command or a guided sequence before creating a
token. Then name the agent and select its sampling cadence. The one-time token becomes a
permanent random agent credential stored with mode `0600`; it can authenticate only agent
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
- **Value** presents a value to copy into an application or hardware target.
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

Each agent row reports four compatibility facts independently: implementation, agent
version, protocol version and computed compatibility. Online state is separate and reports
only whether the server has heard from the agent recently. An offline compatible agent and
an online incompatible record describe different conditions.

## Connectors

Data sources bring telemetry into the same vehicle state and history pipeline without an
agent installed in the vehicle. They appear separately from agents because connection status
describes the server's link to the external system, not whether a vehicle-side agent is
online.

The bundled TeslaMate connector subscribes to TeslaMate's MQTT topics. In Home Assistant,
point it at the same Mosquitto broker that TeslaMate publishes to. Add a data source, select
the vehicle and **TeslaMate (MQTT)**, then provide:

- the broker hostname and port, normally `1883` without TLS;
- TLS settings when the broker requires them, using invalid-certificate acceptance only for
  a broker whose certificate you have verified by another means;
- the optional broker username and password;
- the optional TeslaMate namespace and the numeric car id, normally `1`;
- a sample interval from 1 to 3600 seconds.

The password is write-only. A mask indicates that one is stored, and leaving the password
field empty while editing keeps the existing value. Disabling a source closes its broker
session without deleting history. Changing settings restarts only that source in the worker.

Common TeslaMate values use Carhibou keys such as `battery.soc`, `battery.power`,
`vehicle.odometer`, `vehicle.range`, `charging.active` and the four tyre pressure keys.
Position values feed the normal map and route history. Other values remain available under
the `teslamate.` prefix, such as `teslamate.inside_temp`, for history and dashboards.
