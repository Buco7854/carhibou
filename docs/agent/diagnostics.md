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

The probe listens before writing and classifies each port from what it actually answers.
Each port is tested in its own short-lived process; if opening or reading it hangs, that
process is stopped and reaped before the next port is touched. An unresponsive interface
therefore cannot accumulate hidden owners across retries. No interface index is assumed.

Automatic discovery is saved in `detection.json` to avoid a slow sweep on every restart.
It is reused only while the same serial paths exist. A failed sweep does not erase the
last roles that worked, because those known NMEA and control paths are the safest route
to recovery. Replugging hardware invalidates the saved answer. Explicit
`/dev/serial/by-id/...` choices avoid probing and unstable `ttyUSB` numbering, but they
are not required for self-recovery.

## GPS has no usable position

`gps-info` distinguishes two cases. Valid NMEA traffic without a position means the
receiver is alive but cannot see enough satellites: move the antenna away from the agent
board and metal enclosures and give it a clear view of the sky. No NMEA traffic starts
the same automatic staged recovery as the service; it does not ask the operator to guess
an interface or unplug the Pi.

The normal service performs that recovery in the background while telemetry collection
and its durable outbox continue. It first reuses the last working ports, cycles only the
GNSS engine, then asks the SIMCom firmware to restart. If even its AT control port is
unresponsive, it resets only the physical SIMCom USB device. That final action is
rate-limited to once per 15 minutes and can briefly interrupt a cellular connection; any
unsent samples remain in SQLite and upload afterward. The installer gives the
unprivileged service narrowly scoped permission for this reset—no root service and no
permission over unrelated USB devices.

A stationary fix can repeat valid coordinates, so freshness comes from the receiver's
advancing UTC clock. The agent publishes `gps_fix_age_seconds` and drops a reading that
repeats beyond a window scaled to the sample cadence; a frozen last-known fix cannot
become current position.

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
| SIM7600 serial reconnection and staged recovery | Complete | Passing isolated-process, wake-up, budget, AT-cycle and vendor-scoped USB-reset tests | Failure reproduced on SIM7600/Pi Zero 2026-09-04 and again against a pseudo-serial module; automatic recovery still needs a physical recurrence test |
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
- A serial sweep needs process-isolated per-port watchdogs, a hardware-keyed cache and
  multi-capability classification. Returning from a timed-out goroutine is insufficient:
  it can still own the port and make each later sweep worse.
- A SIM7600 control interface commonly ignores the first command sent after its port is
  opened, and sometimes the second. Asking once files a working port as unknown, and
  since that port is the only one able to switch GNSS on, the module then stays mute
  until it is physically unplugged. A terminal hides this: the operator just presses
  return again.
- A probe watchdog must be derived from a conversation whose windows are truthful. When
  each phase used one fixed read timeout and checked the clock only between reads, every
  phase overran, and the port needing all three phases before it answers is exactly the
  control interface. Sizing the watchdog generously costs nothing: a silent port ends its
  own conversation on time, so only a genuinely wedged one ever waits.
- A stream of valid NMEA sentences proves GNSS is already on; asking an already-running
  SIM7600 to enable it can return an expected error.
- Satellite-fix freshness and receiver liveness are different clocks. Valid no-fix NMEA
  proves the serial path is alive and must not trigger hardware recovery.
