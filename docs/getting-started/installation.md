# Installation

For a server, install Docker with the Compose plugin, clone a tagged VehiNode release,
and copy `.env.example` to `.env`. Generate secrets with `./scripts/generate-env.sh`,
then run:

```bash
docker compose up -d --build
docker compose ps
curl -fsS http://localhost:8000/health/ready
```

Open `http://localhost:8000`. The first registered user receives administrator and
`hooks.manage_code` permissions. Put a TLS reverse proxy in front before exposing it
outside a trusted local network, and set secure cookies in production.

Create a vehicle, choose the experimental C-Zero profile if appropriate, then use
**Devices → Add tracker**. The generated token is short-lived and single-use.
