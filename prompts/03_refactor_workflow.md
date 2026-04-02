# Refactor Workflow (Do Not Break the Product)

## Boundary target

**API → service → repository/data → integrations**

No direct API-to-random-helpers-to-script call chains.

## Rules of engagement

- Keep the app running after every small move.
- Create target folders first; move **one feature at a time**.
- Update imports immediately; don’t leave half-migrated modules.
- Add/extend tests as you move logic (service unit tests first).
- Archive noise by moving it to `scratch/` / `archive/` (don’t delete quickly).

## “10-second rule”

Every time you touch a file, confirm:

- Should this file live here?
- Who should call this (layer ownership)?
- Can a new dev find this in 10 seconds?

