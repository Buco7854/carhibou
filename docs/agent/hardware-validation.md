# Hardware validation ledger

No row below marked “pending” has been physically verified by this project. Simulator,
parser and pseudo-serial tests do not constitute hardware validation.

| Capability | Implementation | Fixture/simulation | Physical hardware |
| --- | --- | --- | --- |
| SQLite offline queue and catch-up | Complete | Passing | Pending Pi/SD endurance |
| SIM7600 RMC/GGA/GST parsing | Complete | Passing | **Confirmed** 2026-08-26, SIM7600 on Pi Zero W: ten consecutive fixes decoded from the `if01` stream, position agreeing with the known location to metres |
| Serial role probing (NMEA/ELM/AT) | Complete | Passing scripted-port tests | **Confirmed** 2026-08-26, Pi Zero W: six interfaces swept, OBDLink SX as `elm`, `if01` as `nmea`, `if03` as `modem`, three abandoned; roles found by answer, never by index |
| GNSS power-on (`AT+CGPS`/`AT+CGNSPWR`) | Complete | Passing response-parsing tests | Pending SIM7600G-H. The 2026-08-26 rejection was the module refusing to switch on a receiver already running, which is expected; the agent no longer asks in that case. Switching a receiver on from cold is still untested |
| `AT+CGPSINFO` position polling | Complete | Passing decode tests | Pending SIM7600G-H |
| SIM7600 serial reconnection | Complete | Passing | Pending SIM7600G-H |
| OBDLink SX discovery/identity | Complete | Passing parser tests | **Confirmed** 2026-08-26: `ELM327 v1.3a`, firmware `STN1130 v4.0.1`, DTC read returned empty with the vehicle off; VIN pending an ignition-on session |
| Standard OBD PID decoding | Complete | Passing | Pending an ignition-on session; the 2026-08-26 run reached the adapter but the vehicle was asleep |
| Hybrid/EV pack charge (PID `5B`) | Experimental | Passing decode test | Pending hybrid/EV; PID semantics unconfirmed |
| Read-only CAN capture/replay | Complete | Passing | Pending vehicle. Monitoring now applies `STFAP` pass filters first, as the proven script does |
| C-Zero battery SOC (`0x374`) | Complete | Passing fixture | Byte offset **corrected** 2026-08-26 from a script proven against a physical C-Zero: charge is byte 1, not byte 0. Live comparison still pending |
| C-Zero pack voltage/current (`0x373`) | Complete | Passing fixture | Offsets agree with the proven script; current **sign reversed** 2026-08-26 to match it. Which direction is charging is still unconfirmed |
| C-Zero pack power sign (charging vs delivering) | Experimental | Passing unit conversion test | **Unconfirmed.** The proven script reports current without stating a direction, so the sign of `battery.power` is a guess until watched during a charge |
| C-Zero speed/odometer (`0x412`) | Complete | Passing fixture | Offsets **confirmed** identical to the proven script |
| Standalone Linux ARMv6 build | Complete | Cross-build and unit tests passing | Pending Pi Zero W |
| Installer on Raspberry Pi OS ARMv6 | Complete | Shell syntax and artifact contract passing | Pending Pi Zero W |

When hardware is tested, record model/revision, OS, agent version, method, evidence and
date here. Never replace “pending” with “verified” from simulation alone.

## Defects found on hardware

- **2026-08-26, from a working C-Zero script.** Monitoring asked the adapter for
  every frame on the bus. A vehicle CAN bus runs at 500 kbit/s and the serial link
  carries 115200, so an unfiltered monitor asks for roughly four times what the
  cable can take; what arrives is truncated. The proven script sets `STFAP` pass
  filters for the identifiers it wants before `STM`, and so does the agent now.
  This is the most likely reason no CAN metric had ever been decoded.
- **2026-08-26, from the same script.** A frame's first data byte was mistaken for
  a displayed length whenever it read as a small decimal — `00` through `08` —
  shifting every offset in that frame by one, and only for those frames. A
  displayed length is a single hex digit, which is now what is required. The
  C-Zero SOC offset had been authored around this, so the two errors had been
  cancelling in the synthetic fixture.

- **2026-08-26, SIM7600G-H on Pi Zero W.** Three of the six interfaces never return
  from being opened: `if02` and `if04` consistently, `if03` intermittently — it
  answered `AT` in one run and blocked in the next moments later. Each costs the
  full watchdog, so a cold sweep spends about 7 s waiting on ports that will never
  answer. Contained rather than solved: the stored answer means a restart does not
  pay it again.
- **2026-08-26, SIM7600G-H on Pi Zero W.** The agent reported `GNSS enable failed`
  while ten good fixes were arriving. The module was right to refuse: the receiver
  was already on, and an enable command answers `ERROR` in that case. The defect was
  the agent asking at all, having failed to establish the receiver's state through an
  interface that answers only intermittently. A GPS path publishing sentences is now
  taken as proof enough and the control port is left shut.

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
