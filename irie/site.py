"""Static site builder: copies the dashboard assets and writes data.json. Output is plain files for any static host."""
from __future__ import annotations

import shutil
from pathlib import Path

WEB = Path(__file__).with_name("web")


def build_site(dataset_json: str, out_dir) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "app.js", "style.css", "_headers"):
        shutil.copyfile(WEB / name, out / name)
    (out / "data.json").write_text(dataset_json, encoding="utf-8")
    return out
