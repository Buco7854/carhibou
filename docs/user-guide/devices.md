# Devices and enrollment

Create an enrollment for the intended vehicle and tracker name, and choose how often the
tracker reads the vehicle and how often it uploads. Both are per tracker, because
trackers on one account are not alike.

A cadence is two pairs, not one: a vehicle is parked for most of the month, and paying
the driving rate for that is what makes a fast cadence unaffordable. The tracker decides
which pair is in force and reports the decision as `vehicle_in_use`, with
`activity_source` naming the evidence.

| Preset   | Driving   | Parked      | Roughly, six signals, driven 1 h/day |
| -------- | --------- | ----------- | ------------------------------------ |
| Live     | 1 s / 1 s | 15 s / 60 s | 267 MB / month                       |
| Standard | 5 s / 5 s | 30 s / 5 m  | 80 MB / month                        |
| Saver    | 15 s      | 60 s / 10 m | 35 MB / month                        |
| Minimal  | 60 s      | 5 m / 30 m  | 8 MB / month                         |

Any field can also be set directly. The figure beside them is calculated from the
tracker's actual upload payload and the number of signals its profile decodes, weighed
by how many hours a day you say the vehicle is driven, so a metered plan can be matched
to a cadence before the tracker is installed rather than after the bill arrives.

Sampling dominates it. Uploading less often only saves per-request overhead and costs
nothing in data, because samples are queued on the tracker until the server acknowledges
them. The estimate assumes the tracker is powered all month; one that only has power
while the vehicle runs uses far less.

## How the tracker knows it is parked

Sources are tried strongest first, and each is allowed to be absent:

1. **A readiness signal the profile decodes.** A profile that maps a frame to
   `vehicle.ready`, `vehicle.ignition` or `charging.active` declares this by doing so;
   no extra profile field is involved. This is authoritative in both directions, so a
   vehicle reporting ignition off is parked whatever else the tracker sees. Charging
   counts as in use, since watching a charge is when a slow cadence is least wanted.
2. **A bus that is still answering.** Most ECUs stop responding shortly after the
   ignition is switched off, which makes this the best evidence a vehicle without a
   profile has. It is taken from whether a frame or PID actually arrived on the last
   read, not from the decoded values, which are republished unchanged after the bus goes
   quiet.
3. **Speed**, decoded or from the GPS fix, above 3 km/h.
4. **Displacement** of more than 60 m, for a receiver that reports no speed at all.

The driving cadence is held for three minutes after the last evidence, so a red light, a
level crossing or a drive-through does not slow the tracker down. A tracker that has just
started has no evidence of anything and begins parked.

**Settings** on the tracker card changes both afterwards. Renaming a tracker does not
disturb it; changing a cadence issues a new configuration version, which the tracker
picks up at its next sync. To apply it immediately, on the tracker run:

```sh
sudo vehinode-agent config --pull
sudo systemctl restart vehinode-agent
```

The installer exchanges
the one-time token for a permanent random device credential, stores it mode `0600`, and
invalidates the token. Device credentials can only use device endpoints.

Revoke lost hardware immediately. Rotation returns the replacement credential once and
invalidates the old value. The tracker card reveals that replacement only for the
current operation so it can be copied immediately. Re-enrollment uses a new enrollment
token.
