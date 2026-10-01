# Migrations

Empty for now — added ahead of the next schema change, not retroactively for
past ones (the module is already `18.0.15.0.0`; every prior version upgraded
cleanly without one).

## Convention

Odoo's own migration-script convention: one folder per version that needs a
data migration, named after the exact version in `__manifest__.py`'s own
`version` key —

```
migrations/
└── 18.0.15.1.0/
    ├── pre-migrate.py    # runs before the ORM registry loads the new code
    ├── post-migrate.py   # runs after, once the new models/fields exist
    └── end-migrate.py    # runs last, after every module has been updated
```

Each script defines a single `migrate(cr, version)` function. Odoo finds and
runs these automatically during `-u furnishing_mes` when the installed
version on the database is older than the one in the manifest — nothing
else needs to reference them.

Bump `__manifest__.py`'s `version` whenever a change needs one of these
scripts, so Odoo actually notices there is a migration to run.
