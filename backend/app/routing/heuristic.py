# a* heuristic.
# h(n) = straight-line distance from n to goal / max speed (turned into minutes).
# it's admissible because every real edge cost is >= base time >= this lower bound,
# so h never overestimates. consistency follows from the triangle inequality.
from __future__ import annotations

from .graph import MAX_SPEED_KMH, Graph


def time_heuristic(graph: Graph, node_id: str, goal_id: str) -> float:
    # lower bound on remaining time from node_id to goal_id, in minutes
    dist_km = graph.straight_line_km(node_id, goal_id)
    hours = dist_km / MAX_SPEED_KMH
    return hours * 60.0
