# boarding-based fare model.
# a passenger pays per LEG (one boarding of one vehicle), not per graph edge:
# base_php covers included_km, then rate_php_per_km beyond. the old model
# summed per-edge fares, which charged a new ticket at every anchor a train
# passed through (north ave -> taft came out ~53 php vs the published ~28).
# a new leg starts exactly where a transfer is charged: trip start, a mode
# change, or a jeepney line change at a real stop (table 3's 0.5 diagonal) -
# riding through a 300m virtual stop or a rail interchange on the same train
# is the same leg.
from __future__ import annotations

import json
import math
from pathlib import Path

from .graph import Edge, Graph

_FARES_PATH = Path(__file__).resolve().parent.parent / "data" / "fares.json"
_MATRICES_PATH = Path(__file__).resolve().parent.parent / "data" / "fare_matrices.json"

# anchors sit at stations under different display names; map them onto the
# official matrix station names per line
_ANCHOR_STATION = {
    "MRT-3": {"SM City North EDSA": "North Avenue MRT", "Cubao Gateway": "Cubao MRT",
              "Shaw Boulevard": "Shaw MRT", "Pasay EDSA-Taft": "Taft Ave MRT"},
    # lrt-1: sm north sits at roosevelt (fernando poe jr.), pasay edsa-taft at
    # edsa station, pitx at pitx station on the cavite extension (in the
    # 2 april 2025 matrix)
    "LRT-1": {"Doroteo Jose": "Doroteo Jose LRT", "Monumento Circle": "Monumento LRT",
              "SM City North EDSA": "Roosevelt LRT", "Pasay EDSA-Taft": "EDSA LRT", "PITX": "PITX LRT"},
    # lrt-2: the doroteo jose anchor boards lrt-2 at recto
    "LRT-2": {"Antipolo LRT-2": "Antipolo LRT", "Cubao Gateway": "Araneta Center-Cubao LRT",
              "Doroteo Jose": "Recto LRT"},
}

# safe defaults if the fares file is missing: flat legacy-ish pricing
_FALLBACK = {"base_php": 13.0, "included_km": 4.0, "rate_php_per_km": 1.8}


def _load_params() -> dict:
    try:
        data = json.loads(_FARES_PATH.read_text(encoding="utf-8"))
        return data["modes"]
    except Exception:
        return {}


_PARAMS = _load_params()


def _load_matrices() -> dict:
    try:
        data = json.loads(_MATRICES_PATH.read_text(encoding="utf-8"))
        return {mode: m.get("matrix", {}) for mode, m in data.items()}
    except Exception:
        return {}


def _load_discounted_matrices() -> dict:
    # the official discounted (student / senior / pwd) matrices where the
    # operator publishes one; today that is the dotr mrt-3 brochure
    try:
        data = json.loads(_MATRICES_PATH.read_text(encoding="utf-8"))
        return {mode: m["discounted_matrix"] for mode, m in data.items() if m.get("discounted_matrix")}
    except Exception:
        return {}


def _load_stored_value_matrices() -> dict:
    # the stored value (beep card) matrices where the operator publishes a
    # separate one; today lrt-1 (lrmc) and lrt-2 (lrta). mrt-3 charges the
    # same fare on a card, so it has no second matrix and keeps its regular one
    try:
        data = json.loads(_MATRICES_PATH.read_text(encoding="utf-8"))
        return {mode: m["stored_value_matrix"] for mode, m in data.items() if m.get("stored_value_matrix")}
    except Exception:
        return {}


def _load_matrix_info() -> dict:
    # where each matrix comes from, shown by /api/status so the fares can be
    # traced back to the published sheet
    try:
        data = json.loads(_MATRICES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    info = {}
    for mode, m in data.items():
        stations = m.get("stations_in_order") or sorted({k.split("|")[0] for k in m.get("matrix", {})})
        info[mode] = {
            "stations": len(stations),
            "effective": m.get("effective"),
            "source": m.get("source"),
            "note": m.get("note"),
            "matrices": [k for k in ("matrix", "discounted_matrix", "stored_value_matrix") if m.get(k)],
        }
    return info


_MATRICES = _load_matrices()
_DISCOUNTED_MATRICES = _load_discounted_matrices()
_STORED_VALUE_MATRICES = _load_stored_value_matrices()
MATRIX_INFO = _load_matrix_info()


def matrix_leg_fare(mode: str, board_name: str, alight_name: str, discounted: bool = False,
                    card: bool = False) -> float | None:
    # official published matrix lookup (e.g. the dotr-mrt3 fare matrix): the
    # exact fare for boarding at one station and alighting at another. with
    # discounted=True the operator's discounted matrix is used when there is
    # one; with card=True the stored value (beep) matrix, else the regular one
    if discounted:
        matrix = _DISCOUNTED_MATRICES.get(mode)
    elif card:
        matrix = _STORED_VALUE_MATRICES.get(mode) or _MATRICES.get(mode)
    else:
        matrix = _MATRICES.get(mode)
    if not matrix:
        return None
    a = _ANCHOR_STATION.get(mode, {}).get(board_name, board_name)
    b = _ANCHOR_STATION.get(mode, {}).get(alight_name, alight_name)
    return matrix.get(f"{a}|{b}")


def mode_params(mode: str) -> dict:
    return _PARAMS.get(mode, _FALLBACK)


def marginal_fare(mode: str, distance_km: float) -> float:
    # the distance-driven part of the fare, used as the per-edge F criterion
    return mode_params(mode)["rate_php_per_km"] * distance_km


def leg_fare(mode: str, leg_km: float) -> float:
    p = mode_params(mode)
    extra_km = max(0.0, leg_km - p["included_km"])
    # fares are charged in whole pesos, rounded up like the published matrices
    return float(math.ceil(p["base_php"] + p["rate_php_per_km"] * extra_km - 1e-9))


def _is_boarding(prev_mode: str, mode: str, at_virtual: bool) -> bool:
    # a new leg starts exactly where a transfer is charged: a mode change, or
    # a jeepney-to-jeepney line change at a real stop (table 3's 0.5 diagonal).
    # rail passing through an interchange on the same train, or any ride
    # continuing through a 300m virtual stop, stays on the same leg.
    if prev_mode != mode:
        return True
    return mode == "Jeepney" and not at_virtual


def path_fare(graph: Graph, edges: list[Edge], discounted: bool = False, card: bool = False) -> float:
    # split the path into boarding legs and price each one. a leg on a line
    # with an official published matrix is priced by its board/alight stations;
    # anything else uses the base + per-km structure. for a student or senior
    # (discounted=True) a leg takes the operator's discounted matrix when one
    # is published, otherwise the paper's 20 percent off the regular leg fare.
    # card=True prices rail legs with the stored value (beep) matrix instead of
    # the single journey ticket; bus and jeepney legs do not change.
    if not edges:
        return 0.0

    def price(mode: str, km: float, board_id: str, alight_id: str) -> float:
        a, b = graph.nodes[board_id].name, graph.nodes[alight_id].name
        if discounted:
            m = matrix_leg_fare(mode, a, b, discounted=True)
            if m is not None:
                return m
        m = matrix_leg_fare(mode, a, b, card=card)
        regular = m if m is not None else leg_fare(mode, km)
        return regular * 0.8 if discounted else regular

    total = 0.0
    leg_mode = edges[0].mode
    leg_km = edges[0].distance_km
    leg_board = edges[0].src
    prev_mode = edges[0].mode
    prev_dst = edges[0].dst
    for e in edges[1:]:
        if _is_boarding(prev_mode, e.mode, graph.nodes[e.src].virtual):
            total += price(leg_mode, leg_km, leg_board, prev_dst)
            leg_mode, leg_km, leg_board = e.mode, e.distance_km, e.src
        else:
            leg_km += e.distance_km
        prev_mode = e.mode
        prev_dst = e.dst
    total += price(leg_mode, leg_km, leg_board, prev_dst)
    return total
