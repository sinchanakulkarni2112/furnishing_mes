# User Manuals

One manual per persona, covering their actual daily workflow in the system as
built across Phases 1-13:

- [`operator-manual.md`](operator-manual.md) — Shop-Floor Terminal: production
  entry, downtime logging, maintenance checklists
- [`supervisor-manual.md`](supervisor-manual.md) — approvals, plan generation,
  operator allocation, maintenance scheduling
- [`plant-manager-manual.md`](plant-manager-manual.md) — executive dashboard,
  master data ownership, alert tuning, monthly MIS
- [`customer-manual.md`](customer-manual.md) — portal login, order tracking,
  support tickets

**On screenshots.** These manuals describe every screen from the actual view
and menu definitions in `addons/furnishing_mes/views/` rather than from
screenshots — this development environment has no browser available, a
limitation noted since Phase 10 (`docs/06-build-plan.md`, Phase 10 finding 5)
and true for every phase after it. The workflows, field names, and button
labels below are read directly from the XML that defines each screen, not
guessed; only the illustrations are missing. Add screenshots from a real
deployment before handing these to end users, if a more visual manual is
wanted.
