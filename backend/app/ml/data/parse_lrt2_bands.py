# parse the lrta march 2026 entry/exit pdf: 5 time-band pages, one row per
# day, 13 stations + total as entry/exit pairs. checks every row sums.
import fitz, re, sys, json, csv
PDF = sys.argv[1]
BANDS = [("05-07", 5, 7), ("07-09", 7, 9), ("17-19", 17, 19), ("05-07", 5, 7), ("09-17", 9, 17), ("19-22", 19, 22)]
doc = fitz.open(PDF)
rows, bad = [], []
for pi in range(doc.page_count):
    txt = doc[pi].get_text()
    m = re.search(r"(\d{1,2})(?:am|pm)?\s*-\s*(\d{1,2})(am|pm)\s*(Peak|Off-Peak)", txt)
    s, e, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "pm" and e != 12: e += 12
    if ap == "pm" and s < e - 12 + 12 and s < 12 and e > 12 and s + 12 < e: s += 12
    if (s, e) == (9, 17) or (s, e) == (9, 5): s, e = 9, 17
    band = (s, e)
    toks = [t.strip() for t in txt.split("\n") if t.strip()]
    i = 0
    while i < len(toks):
        if re.fullmatch(r"\d{1,2}-[A-Z][a-z]{2}", toks[i]) and i + 1 < len(toks) and toks[i+1] in ("Mon","Tue","Wed","Thu","Fri","Sat","Sun"):
            nums = toks[i+2:i+30]
            try:
                vals = [int(n.replace(",", "")) for n in nums]
            except ValueError:
                bad.append((pi, toks[i], "non-number")); i += 1; continue
            ent, ext = vals[0:26:2], vals[1:26:2]
            ok = sum(ent) == vals[26] and sum(ext) == vals[27]
            rows.append({"page": pi, "band": f"{band[0]:02d}-{band[1]:02d}", "start": band[0], "end": band[1],
                         "date": toks[i], "day": toks[i+1], "entries": vals[26], "exits": vals[27], "sums_ok": ok,
                         "station_entries": ent})
            if not ok: bad.append((pi, toks[i], sum(ent), vals[26]))
            i += 30
        else:
            i += 1
print("pages", doc.page_count, "rows", len(rows), "rows not summing", len(bad), bad[:5])
for b in sorted({r["band"] for r in rows}): print(b, sum(1 for r in rows if r["band"] == b), "days")
json.dump(rows, open("lrt2_march2026_bands.json", "w"), indent=0)
