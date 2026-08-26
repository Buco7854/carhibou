# Hardware validation ledger

No row below marked “pending” has been physically verified by this project. Simulator,
parser and pseudo-serial tests do not constitute hardware validation.

| Capability | Implementation | Fixture/simulation | Physical hardware |
| --- | --- | --- | --- |
| SQLite offline queue and catch-up | Complete | Passing | Pending Pi/SD endurance |
| SIM7600 RMC/GGA/GST parsing | Complete | Passing | **Confirmed** 2026-08-26, SIM7600 on Pi Zero W: ten consecutive fixes decoded from the `if01` stream, position agreeing with the known location to metres |
| Serial role probing (NMEA/ELM/AT) | Complete | Passing scripted-port tests | **Confirmed** 2026-08-26, Pi Zero W: six interfaces swept, OBDLink SX as `elm`, `if01` as `nmea`, `if03` as `modem`, three abandoned; roles found by answer, never by index |
| GNSS power-on (`AT+CGPS`/`AT+CGNSPWR`) | Complete | Passing response-parsing tests | **Failing** 2026-08-26: `if03` rejected both `AT+CGPS=1` and `AT+CGNSPWR=1`, though it answers bare `AT`. Not currently exercised, because a streaming receiver is now left alone; a module that boots with GNSS off would still not be recoverable |
| `AT+CGPSINFO` position polling | Complete | Passing decode tests | Pending SIM7600G-H |
| SIM7600 serial reconnection | Complete | Passing | Pending SIM7600G-H |
| OBDLink SX discovery/identity | Complete | Passing parser tests | **Confirmed** 2026-08-26: `ELM327 v1.3a`, firmware `STN1130 v4.0.1`, DTC read returned empty with the vehicle off; VIN pending an ignition-on session |
| Standard OBD PID decoding | Complete | Passing | Pending vehicle |
| Hybrid/EV pack charge (PID `5B`) | Experimental | Passing decode test | Pending hybrid/EV; PID semantics unconfirmed |
| Read-only CAN capture/replay | Complete | Passing | Pending OBDLink/vehicle |
| C-Zero battery SOC (`0x374`) | Experimental | Passing synthetic fixture | Pending real CAN comparison |
| C-Zero pack voltage/current (`0x373`) | Experimental | Passing synthetic fixture | Pending real CAN comparison |
| C-Zero pack power sign (charging vs delivering) | Experimental | Passing unit conversion test | Pending real CAN comparison |
| C-Zero speed/odometer (`0x412`) | Experimental | Passing synthetic fixture | Pending real CAN comparison |
| Standalone Linux ARMv6 build | Complete | Cross-build and unit tests passing | Pending Pi Zero W |
| Installer on Raspberry Pi OS ARMv6 | Complete | Shell syntax and artifact contract passing | Pending Pi Zero W |

When hardware is tested, record model/revision, OS, agent version, method, evidence and
date here. Never replace “pending” with “verified” from simulation alone.

## Defects found on hardware

- **2026-08-26, SIM7600G-H on Pi Zero W.** Three of the six interfaces never return
  from being opened: `if02` and `if04` consistently, `if03` intermittently — it
  answered `AT` in one run and blocked in the next moments later. Each costs the
  full watchdog, so a cold sweep spends about 7 s waiting on ports that will never
  answer. Contained rather than solved: the stored answer means a restart does not
  pay it again.
- **2026-08-26, SIM7600G-H on Pi Zero W.** The agent reported `GNSS enable failed`
  while ten good fixes were arriving. It was opening the control port to switch on a
  receiver that was demonstrably already on, on the interface that answers only
  intermittently. A GPS path that publishes sentences is now taken as proof enough
  and the control port is left shut.

- **2026-08-26, SIM7600G-H on Pi Zero W.** One of the module's interfaces never
  returned from being opened, and the sweep waited on it forever, so every command
  that has to find its devices hung — the telemetry service included. Nothing in Go
  can cancel a blocked syscall, so each port is now given the probe's own budget
  plus a margin — 2.5 s — and abandoned if it does not answer. The interface that blocks is past `if02`; which one, and
  why, is not yet established.

- **2026-08-26, SIM7600G-H on Pi Zero W.** Reopening a serial interface immediately
  after closing it never returned, so every command that probes hardware hung as soon
  as the sweep finished. Fixed by reusing the sweep's own classification instead of
  probing a path twice, and by leaving each interface alone briefly after closing it.
- **2026-08-26, SIM7600G-H on Pi Zero W.** No modem control port was selected, so the
  agent could not switch GNSS on. The cause was the probe, not the hardware: it
  returned at the first capability it found, so the interface streaming NMEA was
  filed as a receiver and never asked whether it also accepted `AT` — which on this
  module is the same interface. Fixed by recording every capability a port has.
  Which interface index carries which capability varies by module and firmware and
  is never inferred from the name.
