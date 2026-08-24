# Agent installation

The tracker targets Raspberry Pi OS/Debian and runs directly under systemd. It does
not require Docker or Node. In **Devices**, create an enrollment token and copy the
generated one-time command:

```sh
curl -fsSL https://vehinode.example/install-agent \
  | sudo sh -s -- --server https://vehinode.example --token ONE_TIME_TOKEN --version 0.1.0
```

The installer validates the OS and HTTPS URL, creates an unprivileged
`vehinode-agent` account, downloads one exact wheel and its SHA-256 file, verifies it,
creates `/opt/vehinode-agent/venv`, enrolls, installs the systemd unit, and runs
diagnostics. The enrollment token expires and is consumed once; the permanent device
credential is returned only to the installer and stored mode-restricted in
`/etc/vehinode-agent`.

The installer is idempotent for its directories, account, environment and service.
To upgrade to a published version:

```sh
sudo vehinode-agent update --version 0.1.1
```

Never modify the command to install a branch or an unversioned “latest” source tree.
