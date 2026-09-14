# processes the government-provided datasets folder into the engine's data
# files. run manually after updating the source files. every output records
# its provenance. sources (obtained by the group through formal data requests):
#   dotr-mrt3 letter + headway table (13 apr 2026, gm capati)
#   dotr edsa busway ridership workbook (daily since jun 2020, hourly station
#     counts, dispatch monitoring)
#   mmda flood reports + summary reports 2024/2025 (incident lat/lng + depth)
#   mmda travel time survey along edsa by bus (6 jan 2025: 17.69 kph average)
#   lrta line 2 coordinates + train intervals
# usage: python -m app.ml.data.process_govt_datasets "<datasets folder>"
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
INCIDENTS_OUT = HERE / "mmda_flood_incidents.json"
BUSWAY_CURVE_OUT = HERE.parent / "models" / "busway_hourly_curve.json"

# metro manila bounding box, drops any mis-parsed coordinate
_BBOX = (14.3, 14.9, 120.8, 121.3)


def merge_flood_incidents(datasets: Path) -> dict:
    sys.path.insert(0, str(HERE))
    from extract_mmda_incidents import parse_pdf

    mmda = datasets / "MMDA"
    rows = []
    for f in ("Flood Report 2024.pdf", "Flood Report 2025.pdf",
              "SUMMARY FLOOD REPORT 2024.pdf", "SUMMARY FLOOD REPORT 2025.pdf"):
        path = mmda / f
        if path.exists():
            got = parse_pdf(str(path))
            print(f"  {f}: {len(got)} incidents")
            rows += got
    seen, unique = set(), []
    for i in rows:
        if not (_BBOX[0] < i["lat"] < _BBOX[1] and _BBOX[2] < i["lng"] < _BBOX[3]):
            continue
        key = (round(i["lat"], 5), round(i["lng"], 5))
        if key in seen:
            continue
        seen.add(key)
        unique.append(i)
    INCIDENTS_OUT.write_text(json.dumps({
        "description": "flood incident points from the mmda flood reports and "
                       "full-year summary reports 2024-2025 (formal data request; "
                       "location, flood depth in inches, lat/lng). used to derive "
                       "the per-edge flood risk baseline.",
        "incidents": unique,
    }, indent=2), encoding="utf-8")
    print(f"  -> {len(unique)} unique incidents written")
    return {"incidents": len(unique)}


def busway_hourly_curve(datasets: Path) -> dict:
    # mean boardings per hour of day at kamuning station (may 2025 sheet of the
    # dotr busway workbook), normalized so the peak hour = 1.5 to match the
    # scale of the mrt-3 demand curve the lstm uses
    import openpyxl

    wb = openpyxl.load_workbook(
        datasets / "DOTr" / "EDSA BUSWAY RIDERSHIP_For requests.xlsx",
        read_only=True, data_only=True)
    ws = wb["MAY 2025_KAMUNING STATION"]
    by_hour: dict[int, list[float]] = {}
    for row in ws.iter_rows(values_only=True):
        time_s, val = row[1] if len(row) > 1 else None, row[3] if len(row) > 3 else None
        if not isinstance(time_s, str) or "-" not in time_s or val is None:
            continue
        try:
            start = time_s.split("-")[0].strip()
            hh = int(start.split(":")[0]) % 12
            if "PM" in start.upper():
                hh += 12
            by_hour.setdefault(hh, []).append(float(val))
        except (ValueError, IndexError):
            continue
    means = {h: sum(v) / len(v) for h, v in by_hour.items()}
    if not means:
        raise SystemExit("no hourly rows parsed from the kamuning sheet")
    peak = max(means.values())
    curve = {h: round(1.5 * m / peak, 3) for h, m in sorted(means.items())}
    BUSWAY_CURVE_OUT.parent.mkdir(parents=True, exist_ok=True)
    BUSWAY_CURVE_OUT.write_text(json.dumps({
        "description": "edsa busway mean hourly boardings, kamuning station, may "
                       "2025 (dotr busway ridership workbook, formal data request). "
                       "normalized peak = 1.5, same scale as the mrt-3 demand curve.",
        "line": "EDSA-Bus",
        "curve": curve,
    }, indent=2), encoding="utf-8")
    print(f"  -> busway curve, {len(curve)} hours, peak hour "
          f"{max(means, key=means.get)}:00 ({int(peak)} boardings)")
    return {"hours": len(curve)}


def main() -> None:
    datasets = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:\Users\ASUS TUF\Documents\3rd Year\2nd Sem\Thesis and SE\Datasets")
    print("merging mmda flood incidents...")
    merge_flood_incidents(datasets)
    print("extracting busway hourly curve...")
    busway_hourly_curve(datasets)
    print("done. retrain the rfr next: python -m app.ml.train_flood")


if __name__ == "__main__":
    main()
