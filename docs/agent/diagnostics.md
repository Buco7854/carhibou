# Agent diagnostics

Useful commands:

```sh
vehinode-agent status
vehinode-agent doctor --probe
vehinode-agent monitor
vehinode-agent logs
vehinode-agent config
vehinode-agent devices
vehinode-agent gps-info --seconds 20
vehinode-agent obd-info
systemctl status vehinode-agent
```

`status` reports installed credentials and durable queue depth. `logs` reads the latest
systemd journal entries.

## Identifying serial ports

A USB product name cannot say which port does what. One SIM7600 publishes five interfaces
under a single identity, and only some answer; picking by name is a guess that leaves the
tracker silently without a position.

The service records what it resolved at startup, so the first thing to check needs no
probing and is safe while telemetry is running:

```sh
vehinode-agent devices
```

Its `detected_by_service` block names the chosen GPS, OBD and control ports and what each
candidate answered.

To probe again yourself, stop the service first: it holds the ports while it runs, and a
second opener would simply be refused.

```sh
sudo systemctl stop vehinode-agent
sudo vehinode-agent doctor --probe
```

`doctor --probe` opens each candidate and reports what it answered:

```json
{"ports": [
  {"device": "/dev/serial/by-id/usb-ScanTool.net_LLC_OBDLink_SX_...", "role": "elm", "identity": "ELM327 v1.3a"},
  {"device": "/dev/serial/by-id/usb-SimTech_..._if02-port0", "role": "modem", "identity": "OK"},
  {"device": "/dev/serial/by-id/usb-SimTech_..._if00-port0", "role": "unknown"}
]}
```

The agent probes the same way whenever a role is set to `auto`, so a working install
normally needs no manual selection. Probing listens before it writes, so a port whose
purpose is unknown is never sent a command it might act on.

Pin a path when you want to skip probing entirely, which also skips its startup cost:

```sh
sudo systemctl stop vehinode-agent
sudo vehinode-agent devices set --gps /dev/serial/by-id/USB_DEVICE \
  --obd /dev/serial/by-id/ANOTHER_DEVICE --modem /dev/serial/by-id/CONTROL_PORT
sudo systemctl start vehinode-agent
```

Pin `--modem` alongside an explicit `--gps`: the control port is what switches the GNSS
receiver on, and an entirely pinned configuration never probes to discover it.

## Watching live data

`monitor` prints the position and vehicle metrics the tracker would sample, once per
interval, so a wiring or antenna fault is visible without waiting for a dashboard round
trip. Stop the service first so it is not holding the ports:

```sh
sudo systemctl stop vehinode-agent
sudo vehinode-agent monitor --interval 2
```

`gps-info` enables the receiver and prints fixes; it fails with an explicit message when
the receiver answers but reports no position, which normally means the antenna needs a
clear view of the sky rather than that the port is wrong. `obd-info` proves the adapter
accepts ELM/STN commands.

## Telling a live fix from a replayed one

A position that repeats is not automatically stale: a parked vehicle reports the same
coordinates all day. The receiver clock is the signal. Poll twice, a minute apart, and
compare the UTC field:

```sh
echo -e "AT+CGPSINFO\r" | sudo tee /dev/serial/by-id/CONTROL_PORT
sleep 60
echo -e "AT+CGPSINFO\r" | sudo tee /dev/serial/by-id/CONTROL_PORT
```

An advancing clock with unchanged coordinates is a healthy stationary fix. A frozen
clock means the module is replaying its last known position, which SIMCom firmware does
instead of reporting empty fields once the receiver loses the sky.

The agent applies the same test. Both position sources report how long they have been
repeating a reading, published as `gps_fix_age_seconds` in device health, and a reading
that stops changing for longer than the freshness window is dropped rather than recorded
as the current position. The window scales with the sampling interval, because holding a
fix far longer than that records where the vehicle was rather than where it is.

## Antenna placement

A receiver that answers commands but never produces a fix is almost always an antenna
problem, not a software one. GPS signals arrive near the noise floor, so keep the antenna
away from the tracker board itself, and give it sky rather than a metal enclosure.

If cellular service is unavailable, do not delete `queue.sqlite3`. Restore networking
and let the next upload acknowledge queued UUIDs. Repeated upload is safe because both
SQLite and PostgreSQL preserve the stable sample ID.

## The vehicle reports position but no metrics

Position and CAN metrics come from two different pieces of hardware, and a tracker whose
adapter never answers still reports its position and health perfectly. The absence of
metric columns in **History** is therefore the expected appearance of a dead OBD path,
not evidence that the vehicle had nothing to say.

The agent publishes `vehicle_source_error` in device health when it knows why it read
nothing, so check that column first. It distinguishes an adapter that never connected
from one that connected and rejected the protocol, and from one that connected but saw
no frame the profile maps.

Run `vehinode-agent obd-info` with the service stopped to talk to the adapter directly.
A reconnection is only attempted once a minute while it keeps failing, so a tracker with
an unplugged adapter still samples its position on schedule.

## A diagnostic that stops after listing the ports

Every command that has to find hardware prints one line per port as it probes it,
then opens what it selected. Stopping right after the last of those lines means the
selected port could not be reopened.

Two things cause that. The service holds the ports it uses, and root is exempt from
the exclusive-access flag that would otherwise refuse a second open, so the command
and the service end up splitting one stream. Stop it first:

```sh
sudo systemctl stop vehinode-agent
```

The commands now say so themselves when the service is running. Separately, a
cellular module's USB serial driver dislikes an interface being reopened the moment
it was closed, so the sweep leaves each one alone briefly and reuses what it already
learned rather than probing the same path twice.

## Reading the sweep

Each line names every capability the port has, not just the one it is filed under:

```
probe /dev/serial/by-id/usb-ScanTool...-if00-port0 -> elm: ELM327 v1.3a
probe /dev/serial/by-id/usb-SimTech...-if01-port0  -> nmea+modem: $GPGGA,...
```

`nmea+modem` is the interesting one: that interface both publishes sentences and
accepts `AT`, so it is used as the position source *and* as the control port that
switches the receiver on. Which interface index does this varies by module and
firmware, so nothing is assumed from the name — a port is only what it answers to.
