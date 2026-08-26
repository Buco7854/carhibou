# Devices and enrollment

Create an enrollment for the intended vehicle and tracker name, and choose how often the
tracker reads the vehicle and how often it uploads. Both are per tracker, because
trackers on one account are not alike.

Four presets cover the usual range, and either field can be set directly. Beside them is
what the choice costs in mobile data over a month of continuous operation, calculated
from the tracker's actual upload payload and the number of signals its profile decodes,
so a metered plan can be matched to a cadence before the tracker is installed rather
than after the bill arrives.

| Preset   | Sample | Upload | Roughly, with a six-signal profile |
| -------- | ------ | ------ | ---------------------------------- |
| Live     | 1 s    | 10 s   | 1.6 GB / month                     |
| Standard | 5 s    | 60 s   | 315 MB / month                     |
| Saver    | 60 s   | 600 s  | 27 MB / month                      |
| Minimal  | 300 s  | 3600 s | 5 MB / month                       |

Sampling dominates that figure; uploading less often only saves the per-request
overhead, and costs nothing in data, because samples are queued on the tracker until the
server acknowledges them. A tracker that only has power while the vehicle runs uses
proportionally less than the table shows.

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
