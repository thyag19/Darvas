# Screenshots

- `before/` - the M2 UI as it stood at the start of M3 (commit `995c39d`, captured by the earlier revision of `tools/capture_screenshots.py`): 17 views, 4 listed as NOT IMPLEMENTED.
- `after/` - the redesigned UI as validated in M4 (M3 UI plus the M4 defect fixes): 27 views, 2 listed as NOT IMPLEMENTED (push/e-mail alerts, G-Sec benchmark). Regenerate with
  `python tools/capture_screenshots.py --out artifacts/screenshots/after`.

Every image is real Chromium rendering of this repository's dashboard using **synthetic demo data** (`irie/demo.py`); every name, number and headline is
invented and none of it is market data. Each folder's README gives how to reach each view.

`after/contact-sheet.png` is a one-image overview of all 27 views (`python tools/contact_sheet.py artifacts/screenshots/after`).
