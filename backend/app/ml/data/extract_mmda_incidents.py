# one-off extractor: pulls flood incident rows out of the two mmda flood report
# pdfs from the group data drive and writes mmda_flood_incidents.json.
# each row in the reports ends with latitude then longitude, with the flood
# depth in inches somewhere after the location name.
# usage: python extract_mmda_incidents.py <report1.pdf> <report2.pdf> ...
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

OUT = Path(__file__).with_name("mmda_flood_incidents.json")

# a data row ends with "<lat> <lng>" where lat is 14.x and lng is 120.x/121.x
_ROW = re.compile(
    r"(?P<body>.+?)\s+(?P<lat>14\.\d{3,})\s+(?P<lng>1[21][01]\.\d{3,})\s*\.?\s*$"
)
_DEPTH = re.compile(r"\b(\d{1,2})\s*(?:\"|inch|in\b)?", re.IGNORECASE)


def parse_pdf(path: str) -> list[dict]:
    incidents = []
    reader = PdfReader(path)
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("CITY", "DATE", "END")):
                continue
            m = _ROW.match(line)
            if not m:
                continue
            body = m.group("body")
            # depth: first small standalone number after the location words,
            # mmda logs depths like `8`, `8"`, sometimes missing
            depth = None
            dm = re.search(r"\b(\d{1,2})\s*\"?\s+(?:metrobase|direct|cctv|fb|messenger|landline)", body, re.I)
            if dm:
                depth = int(dm.group(1))
            # location = leading text up to the depth/source words
            loc = re.split(r"\s+\d{1,2}\s*\"?\s+(?:metrobase|direct|cctv|fb|messenger|landline)", body, flags=re.I)[0]
            loc = re.sub(r"^\s*(?:[A-Za-z ]+City)?\s*\d+\s+", "", loc).strip()
            incidents.append({
                "location": loc,
                "depth_in": depth if depth is not None else 6,  # mmda's typical reading when omitted
                "lat": float(m.group("lat")),
                "lng": float(m.group("lng").rstrip(".")),
            })
    return incidents


def main(paths: list[str]) -> None:
    all_inc = []
    for p in paths:
        rows = parse_pdf(p)
        print(f"{p}: {len(rows)} incidents")
        all_inc.extend(rows)
    # drop exact duplicates (same spot reported in both files)
    seen, unique = set(), []
    for i in all_inc:
        key = (round(i["lat"], 5), round(i["lng"], 5))
        if key in seen:
            continue
        seen.add(key)
        unique.append(i)
    OUT.write_text(json.dumps({
        "description": "flood incident points from the mmda flood reports in the "
                       "group data drive (location, flood depth in inches, lat/lng). "
                       "used to derive the per-edge flood risk baseline.",
        "incidents": unique,
    }, indent=2), encoding="utf-8")
    print(f"wrote {len(unique)} unique incidents -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
