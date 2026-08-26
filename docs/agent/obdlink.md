# OBDLink SX

The agent prefers `/dev/serial/by-id/*OBDLink*` and FTDI identities, then falls back to
`ttyUSB`/`ttyACM`. Its adapter boundary implements ELM/STN commands, identity and
firmware queries, protocol selection, standard OBD queries, read-only CAN monitoring,
one-ID receive filtering and reconnection.

`vehinode-agent obd-info` prints adapter identity, firmware, VIN when service 09 is
available, and diagnostic trouble codes when service 03 is available. Unsupported
services are returned as empty—not treated as an agent failure.

Standard sampling supports engine load, coolant and intake temperature, RPM, vehicle
speed, MAF, throttle, fuel level and control-module voltage. An enabled raw-CAN vehicle
profile selects read-only CAN monitoring instead.

Mode 01 PID `5B` is also sampled and published as `battery.soc`. It is the only standard
route to hybrid/EV pack charge, but few vehicles answer it, SAE J1979 names it "hybrid
battery pack remaining life" rather than state of charge, and it is unverified against a
car. Treat a vehicle profile as the accurate source when one exists. A car that does not
support the PID returns no data and nothing is published, so sampling it costs nothing.

No standard PID reports whether a vehicle is charging. VehiNode derives that from battery
power, which it treats as positive while the pack delivers energy and negative while it
absorbs it; a profile can report `charging.active` and `charging.power` directly instead.

There is no separate CAN device selection in the current agent. Standard OBD queries and
raw CAN monitoring both use the one OBDLink adapter saved as the `obd` device. A future
native SocketCAN provider would expose a distinct network interface selection instead of
pretending that a `can0` interface is a serial port.

VehiNode does not transmit arbitrary CAN frames. See the official
[OBDLink developer documentation](https://www.obdlink.com/developers/) for adapter
command references.
