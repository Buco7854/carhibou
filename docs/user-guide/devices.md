# Devices and enrollment

Create an enrollment for the intended vehicle and tracker name, and choose how often the
tracker reads the vehicle and how often it uploads. Both are per tracker, because
trackers on one account are not alike: a car on a metered connection wants a slower
upload than a daily driver. A slower upload costs nothing in data, only in latency,
since samples are queued on the tracker until they are acknowledged.

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
