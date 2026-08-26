# Agent configuration

The server returns a monotonically versioned configuration during enrollment. The
agent validates a candidate completely before atomically replacing the last-known-good
file. Invalid or older configuration cannot replace a working configuration.

```json
{
  "version": 1,
  "sampling": { "default_seconds": 5, "parked_seconds": 300 },
  "upload": { "default_seconds": 5, "parked_seconds": 300 },
  "vehicle_profile": "citroen-c-zero-v1",
  "vehicle_profile_definition": null
}
```

Sampling and uploading are separate intervals but the presets match them, so a reading
is sent as soon as it is taken. Setting a longer upload interval batches several durable
SQLite samples into one request, which saves the per-request overhead at the cost of a
server that runs behind. The queue remains authoritative through network loss either way
and deletes only sample IDs acknowledged by the server.

The service authenticates and checks for server configuration every five minutes.
Same-version responses cause no file write. A syntactically invalid value, rollback, or
invalid profile definition is rejected before replacing the working file. Both bundled
and owner-created profiles arrive as a validated `vehicle_profile_definition` object
whose `id` must exactly match `vehicle_profile`; that definition is persisted in the
last-known-good file. The standalone executable therefore does not need a separately
installed profile package.

Sampling and upload intervals are set per tracker in **Devices**, at enrollment and
afterwards. `parked_seconds` is optional: a configuration without it uses one cadence in
both states. The tracker decides which state it is in, and publishes that decision as
`vehicle_in_use` alongside the `activity_source` that settled it. Inspect the accepted server configuration with `sudo vehinode-agent config`,
and fetch the server's current one without waiting for the next sync with
`sudo vehinode-agent config --pull`. Pulling stores the configuration; the running
service reloads it at its next sync or immediately on restart. Hardware is
host-local rather than server configuration: the server cannot reliably know which Linux
serial path belongs to a modem or an OBD adapter. Inspect discovery and the current saved
selection with:

```sh
sudo vehinode-agent devices
```

An `auto` source is worked out once and remembered in `detection.json`, and that
answer is reused while the serial paths it was made against are still the ones
present. Each source can be `auto`, `off`, or an explicit path. Save a verified stable choice and
restart the service with:

```sh
sudo vehinode-agent devices set \
  --gps /dev/serial/by-id/usb-SimTech_SIM7600... \
  --obd /dev/serial/by-id/usb-OBDLink_SX...
sudo systemctl restart vehinode-agent
```

Use `--gps off` or `--obd off` when the hardware is intentionally absent. `auto` prefers
recognizable USB identities and otherwise presents conventional `ttyUSB`/`ttyACM`
candidates. Always prefer `/dev/serial/by-id/...` over changing `/dev/ttyUSB0` numbers.
The low-level `run --gps-device` and `run --obd-device` options remain temporary runtime
overrides; normal installations should persist choices through `devices set`.


Serial roles default to `auto`, which probes each candidate port at startup and keeps the
one that answers as expected. Set an explicit path to skip probing, including `--modem`
when the GPS path is pinned, since the control port is what enables the GNSS receiver.
