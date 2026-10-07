# lrt-2 hourly demand curve from the lrta march 2026 entry/exit statistics.
# each band's mean daily entries are spread evenly over its hours; hours
# outside 05:00-22:00 have no service and are left out (the predictor uses the
# curve's minimum there). normalized so the peak hour = 1.5, the same scale as
# the mrt-3 and busway curves.
import json, sys
rows = json.load(open("lrt2_march2026_bands.json"))
out = sys.argv[1]
by = {}
for r in rows:
    by.setdefault((r["start"], r["end"]), []).append(r["entries"])
hourly = {}
for (s, e), v in sorted(by.items()):
    per_hour = sum(v) / len(v) / (e - s)
    for h in range(s, e):
        hourly[h] = per_hour
peak = max(hourly.values())
curve = {h: round(1.5 * x / peak, 3) for h, x in sorted(hourly.items())}
wk = {}
for r in rows:
    if r["day"] not in ("Sat", "Sun"):
        wk.setdefault(r["band"], []).append(r["entries"])
json.dump({
    "description": "lrt-2 mean hourly entries by time band, lrta afc system administration division operational statistics, march 2026 (official), all 31 days, 13 stations. each band's mean daily entries are spread evenly over its hours (05-07, 07-09, 09-17, 17-19, 19-22); no service outside 05:00-22:00. normalized peak = 1.5, same scale as the mrt-3 demand curve.",
    "line": "LRT-2",
    "source": "lrta foi response (tracking LRTA-315199311699), [3] daily entry and exit (peak hours).pdf",
    "band_mean_daily_entries": {f"{s:02d}-{e:02d}": round(sum(v)/len(v)) for (s, e), v in sorted(by.items())},
    "weekday_band_mean_daily_entries": {k: round(sum(v)/len(v)) for k, v in sorted(wk.items())},
    "curve": {str(h): v for h, v in curve.items()},
}, open(out, "w"), indent=2)
print(json.dumps({f"{s:02d}-{e:02d}": round(sum(v)/len(v)) for (s, e), v in sorted(by.items())}))
print(curve)
