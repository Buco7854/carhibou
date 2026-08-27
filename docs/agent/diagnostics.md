# Agent diagnostics

Start with commands that do not open hardware:

```sh
carhibou-agent status
carhibou-agent devices
carhibou-agent logs
carhibou-agent config
systemctl status carhibou-agent
```

`status` reports installed credentials and durable queue depth. `devices` includes the
GPS, OBD and modem roles resolved by the running service. This matters because a cellular
module can expose several serial interfaces under one product name; its label alone does
not identify their jobs.

## Probe and monitor safely

The service keeps serial ports open. Stop it before any diagnostic that opens them too;
otherwise two processes split one byte stream and produce arbitrary results. Hardware
commands refuse while the service is running unless `--force` explicitly accepts that
risk.

```sh
sudo systemctl stop carhibou-agent
sudo carhibou-agent doctor --probe
sudo carhibou-agent gps-info --seconds 20
sudo carhibou-agent obd-info
sudo carhibou-agent monitor --interval 2
sudo systemctl start carhibou-agent
```

The probe listens before writing, classifies every capability a port answers with, and
abandons an unresponsive interface after its budget. An `nmea+modem` port can both emit
position sentences and accept the commands that switch GNSS on. No interface index is
assumed.

Automatic discovery is saved in `detection.json` to avoid a slow sweep on every restart.
It is reused only while the same serial paths exist and the chosen devices still open;
replugging hardware invalidates it. Explicit `/dev/serial/by-id/...` choices avoid both
probing and unstable `ttyUSB` numbering.

## GPS has no usable position

If `gps-info` reaches the receiver but produces no fix, move the antenna away from the
agent board and metal enclosures and give it a clear view of the sky. A stationary fix
can repeat valid coordinates, so freshness comes from the receiver's advancing UTC
clock. The agent publishes `gps_fix_age_seconds` and drops a reading that repeats beyond
a window scaled to the sample cadence; a frozen last-known fix cannot become current
position.

## OBD has no metrics

`carhibou-agent obd-info` separates adapter health from vehicle behavior:

- `supply_voltage` and `protocol` come from the adapter. Roughly 12.4 V suggests a
  resting battery; 13.5 V or more means something is charging it.
- `answers_requests` says whether standard diagnostic requests received a reply. Many
  EVs, including the C-Zero family, legitimately return `NO DATA`.
- `can_frames` and `can_ids` come from passive listening and are the evidence a raw-CAN
  profile needs. A vehicle may answer no request and still broadcast useful frames.

No frames with resting voltage usually means the vehicle is asleep. No frames with
charging voltage suggests the wrong CAN protocol or a diagnostic connector that does
not expose that bus. Because an unfiltered bus exceeds the serial link, an absent ID is
not proof until the relevant profile pass filters are active.

Position and vehicle metrics use different hardware. An agent can report healthy GPS and
no CAN values. In History, inspect `vehicle_source_error`: it distinguishes failure to
connect, a rejected protocol and a connected adapter with no mapped frame. Reconnection
is rate-limited so an unplugged adapter does not interrupt position samples.

If networking fails, do not delete `queue.sqlite3`. Restore connectivity and let normal
uploads acknowledge its stable UUIDs; server and agent deduplication make retries safe.

## Hardware validation ledger

“Pending” means this project has not physically verified the capability. Parser,
simulator and pseudo-serial tests are not hardware validation.

| Capability | Implementation | Fixture/simulation | Physical hardware |
| --- | --- | --- | --- |
| SQLite offline queue and catch-up | Complete | Passing | Pending Pi/SD endurance |
| SIM7600 RMC/GGA/GST parsing | Complete | Passing | **Confirmed** 2026-08-26 on SIM7600 and Pi Zero W: ten fixes matched known location to metres |
| Serial role probing (NMEA/ELM/AT) | Complete | Passing scripted-port tests | **Confirmed** 2026-08-26 on Pi Zero W: six interfaces swept and roles identified by answers, not index |
| GNSS power-on (`AT+CGPS`/`AT+CGNSPWR`) | Complete | Passing response tests | Pending cold start on SIM7600G-H; already-running behavior is handled |
| `AT+CGPSINFO` position polling | Complete | Passing decode tests | Pending SIM7600G-H |
| SIM7600 serial reconnection | Complete | Passing | Pending SIM7600G-H |
| OBDLink SX discovery/identity | Complete | Passing parser tests | **Confirmed** 2026-08-26: ELM327 v1.3a / STN1130 v4.0.1; VIN still pending ignition-on test |
| Standard OBD PID decoding | Complete | Passing | C-Zero confirmed unsupported; pending a vehicle that answers |
| Hybrid/EV pack charge (PID `5B`) | Experimental | Passing decode test | Pending; semantics unconfirmed |
| C-Zero body, brake and tyre (`0x424`, `0x384`, `0x3D3`) | Experimental | Passing fixture | Added from a proven script; lamp-bit interpretation remains uncertain |
| Read-only CAN capture/replay | Complete | Passing | Pending vehicle; monitoring uses profile pass filters |
| C-Zero battery SOC (`0x374`) | Complete | Passing fixture | Offset corrected from a proven physical script; corrected live reading still pending |
| C-Zero pack voltage/current (`0x373`) | Complete | Passing fixture | Offsets match a proven script; current sign corrected |
| C-Zero pack power sign | Complete | Passing conversion test | **Confirmed** 2026-08-26: live AC charge measured 327.2 V, −7.6 A and −2.5 kW; negative means absorbing |
| C-Zero speed/odometer (`0x412`) | Complete | Passing fixture | Offsets confirmed against a proven script |
| Standalone Linux ARMv6 build | Complete | Cross-build and unit tests passing | Pending Pi Zero W |
| Installer on Raspberry Pi OS ARMv6 | Complete | Shell and artifact contract passing | Pending Pi Zero W |

Record model and revision, OS, agent version, method, evidence and date when changing a
physical status. Never promote simulation to verification.

### Reusable lessons from hardware

- Diagnostics must not share live serial streams with the service; continuous CAN
  monitoring makes exclusive ownership essential.
- CAN monitoring must be continuous, try supported protocols and apply profile pass
  filters before reading. Displayed frame length is accepted only in its exact format so
  a payload byte cannot shift every decoder offset.
- A serial sweep needs per-port watchdogs, a hardware-keyed cache and multi-capability
  classification. Some modem interfaces block, and one port may supply both NMEA and AT.
- A stream of valid NMEA sentences proves GNSS is already on; asking an already-running
  SIM7600 to enable it can return an expected error.
