# pdf parser for the mmda flood reports: pulls the incident rows out of one
# report. each row ends with latitude then longitude, with the flood depth in
# inches somewhere after the location name. process_govt_datasets.py calls
# parse_pdf for every report and writes mmda_flood_incidents.json.
from __future__ import annotations

import re

from pypdf import PdfReader

# a data row ends with "<lat> <lng>" where lat is 14.x and lng is 120.x/121.x
_ROW = re.compile(
    r"(?P<body>.+?)\s+(?P<lat>14\.\d{3,})\s+(?P<lng>1[21][01]\.\d{3,})\s*\.?\s*$"
)


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
