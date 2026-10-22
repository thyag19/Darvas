import csv
import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from irie.seed import load_bundle  # noqa: E402

BUNDLE_DIR = ROOT / "tests" / "fixtures" / "invit_workbook_v4"


@pytest.fixture(scope="session")
def fixtures_present():
    """The workbook-derived regression fixtures are third-party-sourced data and are NOT committed (the repo is
    public). Regenerate them locally with tools/extract_workbook_fixtures.py; otherwise these tests skip."""
    if not (BUNDLE_DIR / "distributions.csv").exists():
        pytest.skip("workbook regression fixtures not present (see docs/M1_TECHNICAL.md, 'Regression fixtures')")


@pytest.fixture(scope="session")
def bundle(fixtures_present):
    return load_bundle(BUNDLE_DIR)


@pytest.fixture(scope="session")
def expected(fixtures_present):
    with (BUNDLE_DIR / "expected_screener.csv").open(newline="") as f:
        return {r["key"]: r for r in csv.DictReader(f)}


@pytest.fixture(scope="session")
def as_of(bundle):
    return bundle.as_of
