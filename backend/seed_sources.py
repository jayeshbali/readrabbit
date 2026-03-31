"""
seed_sources.py — One-time script to populate the sources table from data/seed_sources.xlsx.

Usage (from repo root):
    cd backend && python seed_sources.py

Safe to re-run: skips rows where domain already exists.
"""

import os
import sys
import uuid
from pathlib import Path

# Allow running from either repo root or backend/
REPO_ROOT = Path(__file__).parent.parent
EXCEL_PATH = REPO_ROOT / "data" / "seed_sources.xlsx"

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl not installed. Run: pip install openpyxl")
    sys.exit(1)

# Add backend dir to path so we can import database
sys.path.insert(0, str(Path(__file__).parent))

from database import Source, SessionLocal, engine, Base


DOMAIN_OVERRIDES = {
    # Row 49: Excel shows 'www.laphamsquarterly.org' (already used by row 11 Lapham's Quarterly)
    # The actual source for row 49 is Places Journal — fix the domain.
    "Places Journal": "placesjournal.org",
}


def normalise_feed_url(raw: str):
    if not raw:
        return None
    raw = raw.strip()
    if not raw or raw.lower().startswith("n/a"):
        return None
    return raw


def seed():
    if not EXCEL_PATH.exists():
        print(f"ERROR: Excel file not found at {EXCEL_PATH}")
        sys.exit(1)

    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    # Skip header row (row 0)
    data_rows = rows[1:]

    if SessionLocal is None:
        print("ERROR: DATABASE_URL environment variable not set.")
        sys.exit(1)

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    inserted = 0
    skipped = 0

    try:
        for row in data_rows:
            if not row or row[0] is None:
                continue

            # Section header rows have a string in column 0 (e.g. 'SCIENCE & TECHNOLOGY — DEEP')
            if not isinstance(row[0], (int, float)):
                continue

            # Columns: #, Domain, Name, Category, Type, RSS/Feed URL, Pub Frequency, Why
            _, domain_raw, name, category, _type, feed_url_raw, _freq, _why = (
                row + (None,) * (8 - len(row))
            )[:8]

            if not domain_raw or not name:
                continue

            domain = str(domain_raw).strip()
            name = str(name).strip()
            category = str(category).strip() if category else None
            feed_url = normalise_feed_url(str(feed_url_raw) if feed_url_raw else "")

            # Apply manual domain overrides
            if name in DOMAIN_OVERRIDES:
                domain = DOMAIN_OVERRIDES[name]

            # Skip if domain already exists
            existing = db.query(Source).filter(Source.domain == domain).first()
            if existing:
                skipped += 1
                continue

            source = Source(
                id=str(uuid.uuid4()),
                domain=domain,
                name=name,
                category=category,
                source_type="static",
                feed_url=feed_url,
                is_active=1,
            )
            db.add(source)
            inserted += 1

        db.commit()
        print(f"Done. Inserted {inserted} sources, skipped {skipped} (already existed).")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()
        wb.close()


if __name__ == "__main__":
    seed()
