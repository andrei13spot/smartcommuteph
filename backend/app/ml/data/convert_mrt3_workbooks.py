# turns the dotc-mrt3 hourly ridership workbooks (one sheet per month, entry
# and exit per station per hour) into the csv layout train_ridership.py reads:
# one row per hour with the date in the first column ("01-Jan-24"), the hour
# block in the second ("06:00 - 06:59"), the per-station entries and exits,
# and the system total entry and exit in the last two columns.
# usage: python -m app.ml.data.convert_mrt3_workbooks "<2024 workbook>" "<2025 workbook>"
from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).parent


def convert(workbook: Path, year: int) -> Path:
    wb = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    out = HERE / f"mrt3_hourly_{year}.csv"
    header = None
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["DOTC-MRT3 HOURLY RIDERSHIP REPORT", f"converted from {workbook.name}"])
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                if row and row[1] == "TIME" and header is None:
                    header = [c if c else "" for c in row[:30]]
                    w.writerow(["DATE"] + header[1:28] + ["Total Entry", "Total Exit"])
                if not isinstance(row[0], dt.datetime) or not isinstance(row[1], str):
                    continue
                total_entry, total_exit = row[28], row[29]
                if not isinstance(total_entry, (int, float)) or total_entry <= 0:
                    continue  # closed hour or a padding row past the end of the month
                if row[0].year != year:
                    continue
                w.writerow([row[0].strftime("%d-%b-%y"), row[1].strip(),
                            *[("" if c is None else c) for c in row[2:28]], total_entry, total_exit])
                n += 1
    print(f"{workbook.name} -> {out.name}: {n} hourly rows")
    return out


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        p = Path(arg)
        year = 2024 if "2024" in p.name else 2025
        convert(p, year)
