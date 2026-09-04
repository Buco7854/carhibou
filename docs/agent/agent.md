# Vehicle agent

The agent is one CGO-free Go executable for Linux. It embeds its SQLite outbox, serial
support, HTTP client and profile decoder, so the vehicle host needs neither Docker nor
Python. Normal installation uses systemd.

## Install

Create a one-time enrollment under **Data sources** and copy its command:

```sh
curl -fsSL https://carhibou.example/install-agent \
  | sudo sh -s -- --server https://carhibou.example --token ONE_TIME_TOKEN --version 0.1.0
```

The bootstrap validates Linux, systemd and the server URL, detects the CPU, then
downloads one executable and its SHA-256 file. Releases provide `linux-armv6`,
`linux-armv7`, `linux-arm64` and `linux-amd64`. The executable creates the unprivileged
`carhibou-agent` account with serial access, enrolls, installs
`carhibou-agent.service`, and runs diagnostics. Its permanent agent credential is
returned once and stored mode-restricted under `/etc/carhibou-agent`.
Installation also grants that account reset access to SIMCom USB devices only and
disables autosuspend for them. This lets the service recover a wedged SIM7600 without
running as root or resetting the OBD adapter or USB hub.

HTTPS is required by default. A trusted-LAN development server using HTTP adds
`--allow-insecure-http`; that choice is stored so configuration, uploads and updates use
the same policy. Never use it for real credentials on an untrusted network.

Upgrade and removal are owned by the executable:

```sh
sudo carhibou-agent update --version 0.1.1
sudo carhibou-agent uninstall
```

Uninstall requires typing `uninstall` unless automation passes `--yes`. It removes the
service, binary, credentials, saved hardware choices and queued telemetry, and cannot be
undone. Shared operating-system files remain. The installer is idempotent for its own
account, service and directories.

Manual execution works on other Linux systems, but automatic lifecycle needs systemd
and standard account-management, download, checksum and install tools. Retired systems
such as Raspberry Pi OS Stretch should be re-imaged before carrying real credentials;
the ARMv6 binary's ability to run there is not security maintenance.

## Configuration and queue

The server sends monotonically versioned configuration during enrollment and every five
minutes. The agent validates the whole candidate before atomically replacing its
last-known-good file. Older, malformed or mismatched profile definitions cannot replace
a working configuration.

```json
{
  "version": 1,
  "sampling": { "default_seconds": 5, "parked_seconds": 300 },
  "upload": { "default_seconds": 5, "parked_seconds": 300 },
  "vehicle_profile": "citroen-c-zero-v1",
  "vehicle_profile_definition": null
}
```

Sampling and uploading are independent, though presets keep them equal. A longer upload
interval batches durable SQLite rows and saves request overhead while making the server
lag behind. Network loss never discards samples: only IDs acknowledged by the server are
deleted, and retries keep the same stable IDs. Catch-up drains the outbox in requests of
at most 200 samples; every successful request is acknowledged before the next one, so a
later network failure leaves that chunk and everything after it queued for another try.

Inspect or fetch configuration immediately with:

```sh
sudo carhibou-agent config
sudo carhibou-agent config --pull
sudo systemctl restart carhibou-agent
```

For a raw-CAN profile, the adapter listens in bounded one-second bursts at the sampling
cadence. The C-Zero identifiers repeat every 10–100 ms, so one second covers each one
several times without leaving the adapter in a stream indefinitely. While parked, a
one-second wake poll runs once a minute; traffic raises an immediate sample and restores
the driving cadence instead of waiting for the next ten-minute parked sample. Passive
monitoring cannot ask the adapter to discover its protocol, so preparation tries the four
CAN variants until one carries a frame and applies the profile filters before each burst.

## Select serial hardware

The server cannot know which local port belongs to a receiver or OBD adapter. `auto`
probes once, saves the answer in `detection.json`, and reuses it while the same paths
remain available. Each GPS or OBD source can instead be `off` or an explicit path.

```sh
sudo carhibou-agent devices
sudo carhibou-agent devices set \
  --gps /dev/serial/by-id/usb-SimTech_SIM7600... \
  --obd /dev/serial/by-id/usb-OBDLink_SX... \
  --modem /dev/serial/by-id/usb-SimTech_CONTROL...
sudo systemctl restart carhibou-agent
```

Prefer stable `/dev/serial/by-id/...` names. Pin `--modem` with an explicit GPS path
because that control port switches GNSS on. Use `--gps off` or `--obd off` when hardware
is deliberately absent. See [diagnostics](./diagnostics.md) before probing a running
service.

Manual pinning is optional. In `auto`, the service remembers the last working NMEA and
AT roles and recovers them in stages when position traffic genuinely stops: restart the
GNSS engine, ask the SIMCom firmware to restart, then reset only the SIMCom USB parent as
a rate-limited last resort. Discovery probes run in disposable child processes, so an
unresponsive serial interface cannot remain open after its timeout. A valid NMEA stream
without a satellite position is left alone; it needs a clearer sky, not a reset.

## OBDLink and vehicle data

The OBDLink boundary supports ELM/STN identity, firmware and protocol selection,
standard diagnostic queries, read-only CAN monitoring, one-ID filters and reconnection.
`carhibou-agent obd-info` reports adapter details, supply voltage, VIN and trouble codes
when the vehicle supports them. Unsupported services return no value rather than an
agent error.

Standard sampling includes engine load, coolant and intake temperature, RPM, speed,
MAF, throttle, fuel level and control-module voltage. PID `5B` may publish
`battery.soc`, but SAE defines it as hybrid battery remaining life and few vehicles
answer it; a verified profile is the accurate source. No standard PID reports charging.

A raw-CAN profile uses the same saved OBD adapter and never transmits arbitrary vehicle
frames. It applies pass filters before listening so a busy bus does not overwhelm the
serial link. A future native SocketCAN provider would use a separate interface rather
than treating `can0` as a serial path.

## Record and replay CAN

```sh
carhibou-agent can-record drive.jsonl --seconds 120 --profile citroen-c-zero-v1
carhibou-agent replay-can drive.jsonl --profile /path/to/citroen-c-zero-v1.yaml
```

Capture is read-only newline-delimited JSON: a versioned metadata header followed by
timestamped CAN IDs and payloads. Replay stays offline and prints decoded signals without
opening the adapter. Captures may expose locations, identifiers and driving patterns;
scrub them before sharing.

The bundled `citroen-c-zero-v1` profile covers the Mitsubishi i-MiEV and Peugeot iOn
family. Physical evidence currently confirms key battery, speed and odometer formulas;
body, brake and tyre signals retain experimental caveats. The
[hardware ledger](./diagnostics.md#hardware-validation-ledger), not the profile itself,
records that evidence.
