"""Download the NHANES .xpt files used in Part 1 and write a manifest.

Usage (from the repo root):
    python scripts/download_nhanes.py --dry-run   # print the URLs, download nothing
    python scripts/download_nhanes.py             # download missing files, update manifest
    python scripts/download_nhanes.py --verify    # re-hash files on disk against the manifest

Raw files go to data/raw/<cycle>/ (gitignored). The manifest is small and IS committed.
Standard library only.

Part 1 uses four cycles: 2007-08, 2009-10 and 2011-12 (training), 2013-14 (gate).
Files are named <FILE>_<letter>.xpt, for example DEMO_E.xpt for 2007-08.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{year}/DataFiles/{name}.xpt"

# cycle label -> (first year of the release folder, file suffix letter)
CYCLES = {
    "2007-2008": (2007, "E"),
    "2009-2010": (2009, "F"),
    "2011-2012": (2011, "G"),
    "2013-2014": (2013, "H"),
}

# One file per domain.
#   DEMO   demographics            BMX  body measures      GHB  HbA1c
#   DIQ    diabetes questionnaire  SLQ  sleep              DPQ  depression screener (PHQ-9)
#   PAQ    physical activity       DR1TOT  diet, day-1 totals (no individual foods)
FILES = ["DEMO", "BMX", "GHB", "DIQ", "SLQ", "DPQ", "PAQ", "DR1TOT"]

XPT_MAGIC = b"HEADER RECORD*******LIBRARY HEADER RECORD"
MANIFEST = Path("manifest/nhanes_manifest.csv")
RAW_DIR = Path("data/raw")
FIELDS = ["cycle", "file", "url", "bytes", "sha256", "last_modified", "downloaded_utc"]


def planned_files() -> list[tuple[str, str, str]]:
    """Return (cycle, file name, url) for every file in scope."""
    out = []
    for cycle, (year, letter) in CYCLES.items():
        for stem in FILES:
            name = f"{stem}_{letter}.xpt"
            out.append((cycle, name, BASE.format(year=year, name=f"{stem}_{letter}")))
    return out


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict[tuple[str, str], dict]:
    if not MANIFEST.exists():
        return {}
    with MANIFEST.open(newline="") as f:
        return {(r["cycle"], r["file"]): r for r in csv.DictReader(f)}


def save_manifest(rows: dict[tuple[str, str], dict]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for key in sorted(rows):
            w.writerow(rows[key])


def fetch(url: str, dest: Path) -> str:
    """Download to dest, check it is really an XPT file, return the Last-Modified header."""
    req = urllib.request.Request(url, headers={"User-Agent": "nhanes-mlops-demo/0.1"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
        last_modified = resp.headers.get("Last-Modified", "")
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    with tmp.open("rb") as f:
        if f.read(len(XPT_MAGIC)) != XPT_MAGIC:
            tmp.unlink()
            raise ValueError("response is not an XPT file (HTML error page?)")
    tmp.replace(dest)
    return last_modified


def download() -> int:
    manifest = load_manifest()
    failures: list[str] = []
    for cycle, name, url in planned_files():
        dest = RAW_DIR / cycle / name
        key = (cycle, name)
        if dest.exists() and key in manifest:
            print(f"skip   {cycle}/{name}")
            continue
        try:
            last_modified = fetch(url, dest)
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            failures.append(f"{cycle}/{name}  {url}  ({exc})")
            print(f"FAIL   {cycle}/{name}  {exc}")
            continue
        manifest[key] = {
            "cycle": cycle,
            "file": name,
            "url": url,
            "bytes": dest.stat().st_size,
            "sha256": sha256_of(dest),
            "last_modified": last_modified,
            "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"ok     {cycle}/{name}  {dest.stat().st_size:,} bytes")
    save_manifest(manifest)
    if failures:
        print("\nFailed downloads (check the CDC data page for the real file name):")
        print("\n".join(failures))
        return 1
    return 0


def verify() -> int:
    """Check every expected file against the manifest and the disk.

    The expected list comes from the code (planned_files), not from the manifest, so a
    deleted or edited manifest line is reported instead of silently shrinking the count.
    """
    manifest = load_manifest()
    expected = planned_files()
    expected_keys = {(cycle, name) for cycle, name, _ in expected}
    bad = 0
    for cycle, name, _ in expected:
        row = manifest.get((cycle, name))
        path = RAW_DIR / cycle / name
        if row is None:
            print(f"NOT IN MANIFEST   {cycle}/{name}")
            bad += 1
        elif not path.exists():
            print(f"MISSING FILE      {cycle}/{name}")
            bad += 1
        elif sha256_of(path) != row["sha256"]:
            print(f"CHANGED           {cycle}/{name}")
            bad += 1
    extra = sorted(set(manifest) - expected_keys)
    for cycle, name in extra:
        print(f"UNEXPECTED ENTRY  {cycle}/{name} (in the manifest, not in the file list)")
    print(f"verified {len(expected) - bad} of {len(expected)} expected files"
          + (f"; {len(extra)} unexpected manifest entries" if extra else ""))
    return 1 if (bad or extra) else 0


def dry_run() -> int:
    files = planned_files()
    for cycle, name, url in files:
        print(f"{cycle}  {name}  {url}")
    print(f"\n{len(files)} files in scope ({len(CYCLES)} cycles x {len(FILES)} files)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--verify", action="store_true", help="re-hash files against manifest")
    group.add_argument("--dry-run", action="store_true", help="print URLs and exit")
    args = parser.parse_args()
    if args.verify:
        sys.exit(verify())
    if args.dry_run:
        sys.exit(dry_run())
    sys.exit(download())