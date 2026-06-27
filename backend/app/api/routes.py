# routing api endpoints
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import API_TITLE, API_VERSION
from ..ml import flood, ridership
from ..profiles import PROFILES
from ..research.benchmark import run_benchmark
from ..research.inspector import inspect
from ..research.ml_metrics import ml_metrics
from ..routing.graph import load_graph
from ..schemas import (
    AnchorOut,
    CompareRequest,
    CompareResponse,
    NetworkEdgeOut,
    NetworkResponse,
    ProfileOut,
    RouteRequest,
    RouteResponse,
)
from ..services.router_service import build_route

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status")
def status() -> dict:
    # snapshot for the dev dashboard: api liveness, graph size, ml model state
    graph = load_graph()
    undirected = len(graph.edges) // 2
    return {
        "status": "active",
        "service": API_TITLE,
        "version": API_VERSION,
        "graph": {"nodes": len(graph.nodes), "edges": undirected},
        "profiles": len(PROFILES),
        "rainfall_mm": flood.fetch_pagasa_rainfall_mm(),
        "ml_models": [
            {
                "key": "lstm",
                "name": "LSTM Ridership",
                "criterion": "T - ridership",
                "status": "stub",
                "framework": "TensorFlow / Keras (planned)",
                "predictor": ridership.predictor.name,
                "note": "time-of-day demand curve stand-in until the model is trained",
            },
            {
                "key": "rfr",
                "name": "RFR Flood Risk",
                "criterion": "R - flood",
                "status": "stub",
                "framework": "scikit-learn (planned)",
                "predictor": flood.predictor.name,
                "note": "rainfall-scaled baseline; live PAGASA feed pending",
            },
        ],
        "endpoints": [
            "/api/health", "/api/status", "/api/profiles", "/api/anchors",
            "/api/network", "/api/route", "/api/compare",
            "/api/benchmark", "/api/ml-metrics", "/api/inspect",
        ],
    }


@router.get("/profiles", response_model=list[ProfileOut])
def list_profiles() -> list[ProfileOut]:
    return [
        ProfileOut(
            id=p.id, name=p.name, theme=p.theme, priority=p.priority,
            tagline=p.tagline, weights=p.weights,
        )
        for p in PROFILES.values()
    ]


@router.get("/anchors", response_model=list[AnchorOut])
def list_anchors() -> list[AnchorOut]:
    graph = load_graph()
    return [
        AnchorOut(id=n.id, name=n.name, area=n.area, lat=n.lat, lng=n.lng, lines=list(n.lines))
        for n in graph.nodes.values()
    ]


@router.get("/network", response_model=NetworkResponse)
def network() -> NetworkResponse:
    # nodes + undirected edges for the overview map
    graph = load_graph()
    nodes = [
        AnchorOut(id=n.id, name=n.name, area=n.area, lat=n.lat, lng=n.lng, lines=list(n.lines))
        for n in graph.nodes.values()
    ]
    seen: set[tuple[str, str, str]] = set()
    edges: list[NetworkEdgeOut] = []
    for e in graph.edges.values():
        key = (*sorted((e.src, e.dst)), e.mode)
        if key in seen:
            continue
        seen.add(key)
        edges.append(NetworkEdgeOut(from_id=e.src, to_id=e.dst, mode=e.mode))
    return NetworkResponse(nodes=nodes, edges=edges)


@router.post("/route", response_model=RouteResponse)
def route(req: RouteRequest) -> RouteResponse:
    try:
        return build_route(req.origin, req.destination, req.profile, req.hour, req.rainfall_mm)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/benchmark")
def benchmark(hour: int = 8, rainfall_mm: float = 30.0) -> dict:
    # framework vs distance-baseline over all od pairs x profiles (the three sops)
    return run_benchmark(hour=hour, rainfall_mm=rainfall_mm)


@router.get("/ml-metrics")
def ml() -> dict:
    return ml_metrics()


@router.post("/inspect")
def inspect_query(req: RouteRequest) -> dict:
    # query inspector: one od + profile with a per-edge cost decomposition
    try:
        return inspect(req.origin, req.destination, req.profile,
                       req.hour if req.hour is not None else 8,
                       req.rainfall_mm if req.rainfall_mm is not None else 30.0)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest) -> CompareResponse:
    # same origin/destination under all four profiles, for the compare screen
    try:
        routes = [
            build_route(req.origin, req.destination, pid, req.hour, req.rainfall_mm)
            for pid in PROFILES
        ]
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CompareResponse(
        origin=routes[0].origin,
        destination=routes[0].destination,
        routes=routes,
    )
