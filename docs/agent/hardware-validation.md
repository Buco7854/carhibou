# Hardware validation ledger

No row below marked “pending” has been physically verified by this project. Simulator,
parser and pseudo-serial tests do not constitute hardware validation.

| Capability | Implementation | Fixture/simulation | Physical hardware |
| --- | --- | --- | --- |
| SQLite offline queue and catch-up | Complete | Passing | Pending Pi/SD endurance |
| SIM7600 RMC/GGA/GST parsing | Complete | Passing | Pending SIM7600G-H |
| SIM7600 serial reconnection | Complete | Passing | Pending SIM7600G-H |
| OBDLink SX discovery/identity | Complete | Passing parser tests | Pending OBDLink SX |
| Standard OBD PID decoding | Complete | Passing | Pending vehicle |
| Read-only CAN capture/replay | Complete | Passing | Pending OBDLink/vehicle |
| C-Zero battery SOC (`0x374`) | Experimental | Passing synthetic fixture | Pending real CAN comparison |
| C-Zero pack voltage/current (`0x373`) | Experimental | Passing synthetic fixture | Pending real CAN comparison |
| C-Zero speed/odometer (`0x412`) | Experimental | Passing synthetic fixture | Pending real CAN comparison |
| Installer on Raspberry Pi OS ARMv6 | Complete | Shell/CI validation pending | Pending Pi Zero W |

When hardware is tested, record model/revision, OS, agent version, method, evidence and
date here. Never replace “pending” with “verified” from simulation alone.
