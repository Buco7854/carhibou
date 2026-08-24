# Agent diagnostics

Useful commands:

```sh
vehinode-agent status
vehinode-agent doctor
vehinode-agent logs
vehinode-agent config
vehinode-agent devices
vehinode-agent gps-info --seconds 20
vehinode-agent obd-info
systemctl status vehinode-agent
```

`status` reports installed credentials and durable queue depth. `doctor` reports the
platform, saved hardware selection, resolved GPS/OBD paths and all serial candidates.
`logs` reads the latest systemd journal entries.

Discovery is a candidate list, not proof that a serial port speaks the expected protocol.
Stop the service before opening a port in a diagnostic command, test each ambiguous path,
then persist the working path:

```sh
sudo systemctl stop vehinode-agent
sudo vehinode-agent gps-info --device /dev/serial/by-id/USB_DEVICE --seconds 20
sudo vehinode-agent obd-info --device /dev/serial/by-id/ANOTHER_DEVICE
sudo vehinode-agent devices set --gps /dev/serial/by-id/USB_DEVICE \
  --obd /dev/serial/by-id/ANOTHER_DEVICE
sudo systemctl start vehinode-agent
```

For GPS, a real fix proves the selected port emits valid NMEA. For OBD, adapter identity
proves the port accepts ELM/STN commands. A SIM7600 can expose several serial interfaces,
so testing matters even when its USB identity is recognized.

If cellular service is unavailable, do not delete `queue.sqlite3`. Restore networking
and let the next upload acknowledge queued UUIDs. Repeated upload is safe because both
SQLite and PostgreSQL preserve the stable sample ID.
