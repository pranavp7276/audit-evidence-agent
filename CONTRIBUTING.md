# How we work

## Branches and PRs
- `main` is protected: no direct pushes, PR + 1 review, CI green.
- Branch names: `<area>/<short-desc>`, e.g. `db/staging-d4`, `checks/consent`, `pack/gap-report`.
- Small PRs, merged the same day where possible. Pull `main` at least twice a day.
- Every PR that touches `agent/checks/` or `db/staging/` states the eval score before and after.

## Database changes
| You want to | Do this |
|---|---|
| Add or change agent output tables | New file `db/migrations/V###__what.sql` with the next free number |
| Add or fix a typed view over source data | Edit or add `db/staging/R__###_source.sql` |
| Load a new source file | Add it to `data/manifest.yaml`, put the file on the shared drive |
| Try something ad hoc | Do it in your local DB only; never in the shared instance |

If two people pick the same migration number, the runner stops and tells you. The one who merged
second renames to the next number.

## Data
- Raw files live on the shared drive, never in git. Copy them into `data/raw/` at the paths in
  `data/manifest.yaml`, then run `make data-check` to confirm you have the same version as
  everyone else. The data owner regenerates `data/CHECKSUMS.sha256` when files change.

## Decisions
Any ruling on how to interpret a rule or the data goes in `docs/decisions.md` the same day,
with a one-line reason. Code that implements it links the decision id (e.g. `# D-007`).

## Daily sync (15 min)
1. Latest eval score on the public requests.
2. Board: what moved, what's blocked.
3. Open decisions: settle or assign.
