# CAN recording and replay

Capture is read-only and writes portable newline-delimited JSON:

```sh
vehinode-agent can-record drive.jsonl --seconds 120 --profile citroen-c-zero-v1
vehinode-agent replay-can drive.jsonl --profile /path/to/citroen-c-zero-v1.yaml
```

The first record is a versioned header with capture, adapter, device and profile
metadata. Each following record contains a Unix timestamp, hexadecimal CAN ID and
payload. Replay never opens the vehicle adapter; it decodes offline and prints the
signals produced by the selected profile.

Captures can contain location, vehicle identifiers, driving patterns and other private
data. Scrub them before publishing. Raw replay is intentionally **offline only** in v1.
