# Hardware validation ledger

No row below marked “pending” has been physically verified by this project. Simulator,
parser and pseudo-serial tests do not constitute hardware validation.

| Capability | Implementation | Fixture/simulation | Physical hardware |
| --- | --- | --- | --- |
| SQLite offline queue and catch-up | Complete | Passing | Pending Pi/SD endurance |
| SIM7600 RMC/GGA/GST parsing | Complete | Passing | Sentences seen on `if01` 2026-08-26 (`GPGSV`, `PQXFI`); fix decoding pending |
| Serial role probing (NMEA/ELM/AT) | Complete | Passing scripted-port tests | **Confirmed** 2026-08-26, Pi Zero W / Raspberry Pi OS: classified OBDLink SX as `elm` (`ELM327 v1.3a`) and SimTech `if01` as `nmea` from a live sentence |
| GNSS power-on (`AT+CGPS`/`AT+CGNSPWR`) | Complete | Passing response-parsing tests | **Unreachable** 2026-08-26: no interface answered `AT`, so `if00` classified `unknown` and no control port was selected |
| `AT+CGPSINFO` position polling | Complete | Passing decode tests | Pending SIM7600G-H |
| SIM7600 serial reconnection | Complete | Passing | Pending SIM7600G-H |
| OBDLink SX discovery/identity | Complete | Passing parser tests | Identity **confirmed** 2026-08-26 (`ELM327 v1.3a`); vehicle session pending |
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

- **2026-08-26, SIM7600G-H on Pi Zero W.** Reopening a serial interface immediately
  after closing it never returned, so every command that probes hardware hung as soon
  as the sweep finished. Fixed by reusing the sweep's own classification instead of
  probing a path twice, and by leaving each interface alone briefly after closing it.
- **2026-08-26, SIM7600G-H on Pi Zero W.** No interface answered `AT`, so no modem
  control port was selected and the agent cannot switch GNSS on. The receiver was
  already emitting NMEA on `if01`, which is why position still worked; a module that
  boots with GNSS powered down would report nothing and the agent could not fix it.
  Not yet diagnosed: `if00` answered neither `ATI` nor `AT` within the probe window.
