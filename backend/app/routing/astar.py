# constraint-aware multi-criteria a*.
# the state is (node, arriving_mode) because the transfer term depends on how we
# got to the node. f(n) = g(n) + h(n). we also count expanded states for the
# search-space efficiency question (rq3).
from __future__ import annotations

import heapq
from dataclasses import dataclass

from ..profiles import Profile
from .cost import CostContext
from .graph import Edge, Graph
from .heuristic import time_heuristic


@dataclass
class RouteResult:
    edges: list[Edge]          # edges from origin to destination in order
    total_cost: float          # accumulated weighted cost
    expanded_nodes: int        # states popped from the frontier (rq3)
    found: bool
    expanded_order: list[str]  # node ids in the order a* expanded them (for playback)


def shortest_route(
    graph: Graph,
    origin: str,
    destination: str,
    profile: Profile,
    ctx: CostContext,
) -> RouteResult:
    if origin not in graph.nodes or destination not in graph.nodes:
        raise KeyError("origin and destination must be known anchor ids")
    if origin == destination:
        return RouteResult(edges=[], total_cost=0.0, expanded_nodes=0, found=True, expanded_order=[])

    start_state = (origin, None)  # (node, arriving_mode)
    g_score: dict[tuple[str, str | None], float] = {start_state: 0.0}
    came_from: dict[tuple[str, str | None], tuple[tuple[str, str | None], Edge]] = {}

    counter = 0  # tie-breaker so the ordering is stable
    h0 = time_heuristic(graph, origin, destination)
    frontier: list[tuple[float, int, tuple[str, str | None]]] = [(h0, counter, start_state)]
    visited: set[tuple[str, str | None]] = set()
    expanded = 0
    order: list[str] = []  # station ids in expansion order, for the playback

    while frontier:
        _, _, state = heapq.heappop(frontier)
        if state in visited:
            continue
        visited.add(state)
        expanded += 1

        node, arriving_mode = state
        if not order or order[-1] != node:
            order.append(node)
        if node == destination:
            return _reconstruct(came_from, state, g_score[state], expanded, order)

        for edge in graph.neighbors(node):
            nxt = (edge.dst, edge.mode)
            if nxt in visited:
                continue
            tentative = g_score[state] + ctx.edge_cost(edge, arriving_mode, profile)
            if tentative < g_score.get(nxt, float("inf")):
                g_score[nxt] = tentative
                came_from[nxt] = (state, edge)
                f = tentative + time_heuristic(graph, edge.dst, destination)
                counter += 1
                heapq.heappush(frontier, (f, counter, nxt))

    return RouteResult(edges=[], total_cost=float("inf"), expanded_nodes=expanded, found=False, expanded_order=order)


def _reconstruct(came_from, state, total_cost: float, expanded: int, order: list[str]) -> RouteResult:
    # walk the came_from links back to the start
    edges: list[Edge] = []
    cur = state
    while cur in came_from:
        prev, edge = came_from[cur]
        edges.append(edge)
        cur = prev
    edges.reverse()
    return RouteResult(edges=edges, total_cost=total_cost, expanded_nodes=expanded, found=True, expanded_order=order)
