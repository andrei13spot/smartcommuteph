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


_MATRICES = _load_matrices()


def matrix_leg_fare(mode: str, board_name: str, alight_name: str) -> float | None:
    # official published matrix lookup (e.g. the dotr-mrt3 fare matrix): the
    # exact fare for boarding at one station and alighting at another
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


def path_fare(graph: Graph, edges: list[Edge]) -> float:
    # split the path into boarding legs and price each one. a leg on a line
    # with an official published matrix is priced by its board/alight stations;
    # anything else uses the base + per-km structure.
    if not edges:
        return 0.0

    def price(mode: str, km: float, board_id: str, alight_id: str) -> float:
        m = matrix_leg_fare(mode, graph.nodes[board_id].name, graph.nodes[alight_id].name)
        return m if m is not None else leg_fare(mode, km)

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
