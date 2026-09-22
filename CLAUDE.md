# Working on this repo

- **Nix for everything** (/use-nix): run tools through `nix develop -c …` (Python, Node, sqlite come from `flake.nix`); add dependencies to the flake, never globally. `nix` may not be on PATH in agent shells: use `/nix/var/nix/profiles/default/bin/nix`. After changing `web/package-lock.json`, refresh `npmDepsHash` (`nix build .#web` prints it).
- **Verify** before committing: `pytest`, `npm --prefix web run check`, `npm --prefix web run build`, and `nix build` for packaging changes. For UI changes, look at the running app (screenshots), not just the type-checker.
- **Docs** (/docky): decisions → `docs/adr/`, change sets → `docs/changelog/`, open work → `docs/TODO.md`, index in `docs/INDEX.md`. Timestamped names `YYYY-MM-DD-HHMM-slug.md`.
- **Commits** (/version-commit): subject `[X.Y.Z] summary`; Z per commit, Y per branch, set `version` in `pyproject.toml`, `flake.nix`, and `web/package.json` to match. The bump also changes the version in `web/package-lock.json` (run `npm --prefix web install --package-lock-only`), which changes the hash, so every bump needs a new `npmDepsHash`: run `nix build .#web`, copy the `got:` hash into `flake.nix`, then run `nix build` again before committing.
- Don't run migrations or purges against `data/uta.db` to test things; copy it first (the stale-data purge is irreversible).
