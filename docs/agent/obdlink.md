# OBDLink SX

The agent prefers `/dev/serial/by-id/*OBDLink*` and FTDI identities, then falls back to
`ttyUSB`/`ttyACM`. Its adapter boundary implements ELM/STN commands, identity and
firmware queries, protocol selection, standard OBD queries, read-only CAN monitoring,
one-ID receive filtering and reconnection.

`vehinode-agent obd-info` prints adapter identity, firmware, VIN when service 09 is
available, and diagnostic trouble codes when service 03 is available. Unsupported
services are returned as empty—not treated as a tracker failure.

Standard sampling supports engine load, coolant and intake temperature, RPM, vehicle
speed, MAF, throttle, fuel level and control-module voltage. An enabled raw-CAN vehicle
profile selects read-only CAN monitoring instead.

There is no separate CAN device selection in the current agent. Standard OBD queries and
raw CAN monitoring both use the one OBDLink adapter saved as the `obd` device. A future
native SocketCAN provider would expose a distinct network interface selection instead of
pretending that a `can0` interface is a serial port.

VehiNode does not transmit arbitrary CAN frames. See the official
[OBDLink developer documentation](https://www.obdlink.com/developers/) for adapter
command references.
