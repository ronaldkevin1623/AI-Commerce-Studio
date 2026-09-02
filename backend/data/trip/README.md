# Sector datasets

Static reference data for a sector plug-in. There was no convention for this
before: the merchant catalogue lives inline in `store.py` and the red-team
corpus in `attacks.py`, which is right for a few dozen hand-written records
and wrong for a few hundred thousand rows of CSV.

    raw/        the files exactly as supplied, never edited by hand
    *.sqlite    compact indexes built from raw/ by build.py

`raw/` is gitignored — the three trip CSVs are ~175 MB together and do not
belong in version control. The build step produces a small queryable index
that does, or can be regenerated in one command from the raw files.

Anything served from here is dataset-backed, not live. An adapter reading
this directory must say so: `can_fulfil = False`, and the UI labels it as a
snapshot with the date it was supplied. That is the same rule the eBay and
merchant adapters follow about what they can and cannot promise.
