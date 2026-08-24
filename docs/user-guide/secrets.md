# Hook secrets

Create secrets by name in the Hooks screen. Values are encrypted under the application
master key and never returned after creation; the UI only receives a mask. Use
`ctx.secrets["name"]`. Log output and tracebacks are redacted against current secret
values, but privileged hook code can deliberately transmit accessible secrets.

Back up `VEHINODE_MASTER_KEY` separately with the database. Without it, stored secrets
cannot be recovered.
