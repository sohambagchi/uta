# Background collector and migration guard

- `deploy/install-collector.sh`: pinned build + `uta-collector.service` (systemd user unit, restarts on failure).
- `serve` opens the database read-only for requests and won't migrate without `--migrate`.
- All commands refuse a database with a newer schema version (exit code 2).
- Migrations back the database up first to `<db>.pre-vN-<time>.bak`.
- New `uta snapshot [dest]` (default `data/dev.db`).
- `up` builds the app before starting its collector thread, so only one of them migrates.
- Rationale: see ADR [2026-09-21-2200-background-collector](../adr/2026-09-21-2200-background-collector.md)
