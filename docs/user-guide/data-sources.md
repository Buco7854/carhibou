# Data sources

Data sources are the ways telemetry reaches a vehicle. An agent pushes data from
vehicle hardware; a connector receives data from an external service. Both feed the
same live state, history, dashboards and hooks.

## Add an agent

Open **Data sources**, choose **Add agent**, then:

1. Select an implementation and review its hardware and setup instructions.
2. Choose the vehicle, name the agent and select its CAN profile.
3. Pick a sampling cadence and create the one-time enrollment token.
4. Follow the displayed command or guided setup before the token expires.

![Enrolled agents with their cadence](/screens/agents.png)

The token becomes a permanent random credential stored on the device with mode `0600`.
It authenticates only agent routes. If setup fails, create a new one-time token rather
than reusing the old one.

## Add a TeslaMate connector

The bundled connector subscribes to TeslaMate's MQTT topics. In Home Assistant, point
it at the same Mosquitto broker that TeslaMate publishes to. Choose **Add connector**,
select the vehicle and **TeslaMate (MQTT)**, then provide:

- the broker hostname and port, normally `1883` without TLS;
- TLS settings when required, accepting an invalid certificate only after verifying the
  broker another way;
- the optional broker username and password;
- the optional TeslaMate namespace and numeric car id, normally `1`;
- the bundled `teslamate-mqtt-v1` mapping profile;
- a sample interval from 1 to 3600 seconds.

The password is write-only. A mask shows that one is stored, and leaving the password
blank while editing keeps it. Disabling the connector closes its broker session without
deleting history. Changing settings restarts only that connector.

## Manage a source

An agent's **Settings** changes its CAN profile or cadence and creates a new configuration
version. Apply it immediately instead of waiting for the next sync:

```sh
sudo carhibou-agent config --pull
sudo systemctl restart carhibou-agent
```

Revoke lost hardware immediately. Credential rotation invalidates the old credential
and shows its replacement once, so copy it during the operation. Re-enrollment always
uses a new single-use token. See [agent installation and configuration](/agent/agent)
for host setup and hardware selection.

Compatibility and connectivity are separate. An agent row reports its implementation,
agent version, protocol version and compatibility; online state says only whether the
server has heard from it recently. A connector instead reports the server's connection
to the external system.

## Reporting cadence

Agents use separate driving and parked rates because most vehicles spend most of the
month parked. Choose a preset during enrollment or enter custom values:

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
about 30 seconds. Estimates use the selected CAN profile's signal count and expected
driving hours.

The agent reports its decision as `vehicle_in_use`, with `activity_source` naming the
evidence: `readiness`, `engine`, `speed`, `movement`, `grace` or `idle`. It considers, in
order, profile readiness, engine speed above zero, decoded or GPS speed above 3 km/h, and
displacement above 60 m. Any source may be absent. Charging is not among them: a car on a
charger is parked, and its charge is reported by the start and stop events instead. Driving cadence remains active for three minutes after the last evidence to
avoid slowing down at brief stops; a newly started agent begins parked.

## Custom agents

Choose the built-in `custom` implementation for an independently developed agent. Its
guided setup provides the server URL, one-time token, protocol version and protocol
documentation separately. A custom agent uses the same enrollment, configuration and
telemetry endpoints as the bundled Go agent.

Setup instructions may contain command, value, link and manual steps. An enrollment is
bound to the selected implementation, and the server checks protocol compatibility
before consuming the token so a mismatch can be corrected without creating another
enrollment.

Maintained implementations use an `agent.toml` manifest to describe their name, hardware
and setup steps. See [the agent protocol](/developers/architecture#agent-protocol) for
the implementation contract.

## Mapping source data

Profiles translate source-specific input into Carhibou's canonical readings. CAN
profiles can be selected only for agents; mapping profiles can be selected only for
connectors.

The TeslaMate profile maps common values to keys such as `battery.soc`,
`battery.power`, `vehicle.odometer`, `vehicle.range`, `charging.active` and the four tyre
pressure keys. Position feeds the normal map and route history. Other values remain
available under the `teslamate.` prefix for history and dashboards. Changing a mapping
profile restarts that connector with a new configuration version.
