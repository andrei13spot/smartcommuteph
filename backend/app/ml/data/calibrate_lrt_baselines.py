# sets the lrt-1 and lrt-2 crowding baselines in graph.json from the psa
# table 13-2 average daily load factor (2024 mean), relative to mrt-3:
#   line baseline = mrt-3 baseline mean x (line load factor / mrt-3 load factor)
# load factor is riders over capacity, so it is the line's crowding level; the
# hour-by-hour shape still comes from each line's demand curve. lrt-1 edges
# keep their relative differences (scaled to the new mean).
# usage: python -m app.ml.data.calibrate_lrt_baselines
import csv, json, statistics as st
from pathlib import Path

HERE = Path(__file__).parent
GRAPH = HERE.parent.parent / "data" / "graph.json"
OPERATOR = {"LRT-1": "LRT Line 1", "LRT-2": "LRT Line 2", "MRT-3": "MRT Line 3"}


def load_factors(year_cols=slice(12, 24)):
    lf = {}
    for r in csv.reader(open(HERE / "psa_table_13-2_rail_ridership.csv", encoding="utf-8")):
        if "Load Factor" not in r[1]:
            continue
        for mode, key in OPERATOR.items():
            if key in r[0]:
                lf[mode] = st.mean(float(x) for x in r[2:][year_cols])
    return lf


def main():
    lf = load_factors()
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    mrt = st.mean(e["ridership"] for e in g["edges"] if e["mode"] == "MRT-3")
    for mode in ("LRT-1", "LRT-2"):
        edges = [e for e in g["edges"] if e["mode"] == mode]
        target = round(mrt * lf[mode] / lf["MRT-3"], 3)
        old = st.mean(e["ridership"] for e in edges)
        for e in edges:
            e["ridership"] = round(e["ridership"] * target / old, 3)
        print(f"{mode}: load factor {lf[mode]:.2f}% vs mrt-3 {lf['MRT-3']:.2f}% -> mean baseline {old:.3f} -> {target:.3f}")
    GRAPH.write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
