# Rename: VehiNode → Carhibou

The product is renamed. Display name **Carhibou**, technical identifier
**carhibou**. Backward compatibility is waived — no aliases, no fallbacks to old
names. The GitHub repo will be renamed to `Buco7854/carhibou` by the
orchestrator at push time; write the new paths now.

## Name mapping (exact)

| Old | New |
| --- | --- |
| VehiNode (display) | Carhibou |
| vehinode (technical) | carhibou |
| `VEHINODE_` env prefix (settings, CI, compose, Dockerfile, scripts, e2e server) | `CARHIBOU_` |
| Python distribution `vehinode` (pyproject name) | `carhibou` |
| Go module `github.com/Buco7854/vehinode/agent` | `github.com/Buco7854/carhibou/agent` |
| binary `vehinode-agent` | `carhibou-agent` |
| systemd `vehinode-agent.service` | `carhibou-agent.service` |
| agent config/data dirs (`/etc/vehinode-agent`, `/var/lib/vehinode-agent` or whatever agentsystem declares) | same with `carhibou-agent` |
| release artifacts `vehinode-agent-<ver>-<target>` | `carhibou-agent-<ver>-<target>` |
| `/opt/vehinode-agent-releases` | `/opt/carhibou-agent-releases` |
| image `ghcr.io/buco7854/vehinode` | `ghcr.io/buco7854/carhibou` (workflows that derive from `github.repository` need no literal) |
| cookies (`vehinode_session`?, `vehinode_oidc`, CSRF cookie if prefixed) | `carhibou_*` |
| compose project/db/user names `vehinode` | `carhibou` |
| entrypoint `vehinode-entrypoint` | `carhibou-entrypoint` |
| default sqlite filenames / worker ids / user agent strings containing vehinode | carhibou |
| docs site URL `buco7854.github.io/vehinode` | `buco7854.github.io/carhibou` |

Unchanged: route paths (`/install-agent`, `/api/v1/...`), database schema, the
`Buco7854` owner, license, and anything whose name never contained the brand.

## Rules

- The rename is case-preserving: VehiNode→Carhibou, vehinode→carhibou,
  VEHINODE→CARHIBOU. Grep case-insensitively when done; zero matches outside
  `.git/` and `.agent/` history notes.
- `go.mod` module line changes and EVERY Go import path with it; `gofmt`,
  `go build ./...`, `go vet ./...`, `go test ./...` must pass.
- The installer script, agent update flow, and CI smoke test reference artifact
  and binary names — keep them mutually consistent (CI downloads
  `/agent/releases/<ver>/carhibou-agent-<ver>-linux-amd64` and runs it).
- Backend: settings env_prefix, cookie names, user-visible strings, OpenAPI
  titles, log worker ids. Tests updated accordingly.
- Do not rename Python module directories (`backend/app/...` has no brand in
  paths) — only the distribution name and strings.
