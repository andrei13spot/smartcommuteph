# parse every lrta monthly entry/exit file: read the whole document as one
# token stream, carry the last band heading forward, keep a day row only if
# its 13 station entries and exits add up to the printed totals.
import fitz, re, sys, glob, json, os, datetime as dt
MONTHS = {m: i for i, m in enumerate(["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE","JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"], 1)}
DAYS = {"Mon","Tue","Wed","Thu","Fri","Sat","Sun"}
BAND_RX = re.compile(r"^(\d{1,2})(am|pm)?\s*-\s*(\d{1,2})(am|pm)\s*(?:Off-)?Peak", re.I)

def band_of(tok):
    m = BAND_RX.match(tok)
    if not m: return None
    s, sa, e, ea = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4).lower()
    e24 = e + 12 if ea == "pm" and e != 12 else e
    if sa: s24 = s + 12 if sa.lower() == "pm" and s != 12 else s
    else: s24 = s + 12 if ea == "pm" and s + 12 < e24 else s
    return (s24, e24)

def parse(path):
    doc = fitz.open(path)
    toks = [t.strip() for p in doc for t in p.get_text().split("\n") if t.strip()]
    title = " ".join(toks[:12]).upper()
    m = re.search(r"MONTH OF\W*([A-Z]+)[^0-9]*?(?:\d{1,2}\s*-\s*\d{1,2},?\s*)?(\d{4})", title)
    month, year = MONTHS[m.group(1)], int(m.group(2))
    rows, bad, band, i = [], [], None, 0
    while i < len(toks):
        b = band_of(toks[i])
        if b: band = b; i += 1; continue
        if re.fullmatch(r"\d{1,2}-[A-Za-z]{3}", toks[i]) and i + 1 < len(toks) and toks[i+1] in DAYS:
            try:
                vals = [int(x.replace(",", "")) for x in toks[i+2:i+30]]
            except ValueError:
                bad.append((toks[i], "short")); i += 2; continue
            ent, ext = vals[0:26:2], vals[1:26:2]
            day = int(toks[i].split("-")[0])
            if sum(ent) == vals[26] and sum(ext) == vals[27] and band:
                rows.append({"date": dt.date(year, month, day).isoformat(), "weekday": toks[i+1],
                             "band": f"{band[0]:02d}-{band[1]:02d}", "start": band[0], "end": band[1],
                             "entries": vals[26], "exits": vals[27], "station_entries": ent})
            else:
                bad.append((toks[i], band, sum(ent), vals[26]))
            i += 30; continue
        i += 1
    return year, month, rows, bad

allrows, report = [], []
for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.pdf"))) + [sys.argv[2]]:
    if "RIDERSHIP DATA" in f: continue
    y, mth, rows, bad = parse(f)
    per = {}
    for r in rows: per.setdefault(r["band"], set()).add(r["date"])
    report.append((f"{y}-{mth:02d}", len(rows), {k: len(v) for k, v in sorted(per.items())}, len(bad)))
    allrows += rows
for r in sorted(report): print(r)
keys = {(r["date"], r["band"]) for r in allrows}
print("rows", len(allrows), "unique day-bands", len(keys))
json.dump(allrows, open("lrt2_all_bands.json", "w"))
