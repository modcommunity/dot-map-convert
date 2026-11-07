# Proposed audit exemptions

`tools/audit_maps.py` reads `<maps repository>/tools/audit_exempt.json` (see its docstring). The files here are the proposed contents for the repositories whose documents were audited on 2026-11-07 against fresh imports (the committed documents are not regenerated yet, so the numbers are those of a re-import with the repository's `ports.txt` flags and the importer at this commit). Copy a file to the repository when its documents are regenerated; an entry whose loss is back under the limit is reported as "no longer needed".

Each ceiling is the measured loss rounded up to a thousandth, so a new loss still fails. Every row names the importer passes behind the loss (measured by `tools/audit_passes.py`: put one pass's removed boxes back and see how many lost brushes and floor samples return) and why that pass is intended.
