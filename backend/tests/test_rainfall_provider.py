# the met norway rainfall provider: parser against a real recorded response,
# and the provider chain's offline behavior. no network in any test.
from __future__ import annotations

import json
from pathlib import Path

from app.ml import flood

_FIXTURE = Path(__file__).parent / "fixtures" / "metno_manila_2026-09-10.json"


def test_metno_parser_on_real_recorded_response():
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    mm = flood._metno_rainfall_24h(payload)
    assert mm is not None
    # a 24h manila total must be a sane magnitude (0..500mm), matching the
    # scale the rfr was trained on
    assert 0.0 <= mm <= 500.0


def test_metno_parser_prefers_hourly_blocks():
    payload = {"properties": {"timeseries": [
        {"time": "t", "data": {"next_1_hours": {"details": {"precipitation_amount": 1.0}}}}
        for _ in range(24)
    ]}}
    assert flood._metno_rainfall_24h(payload) == 24.0


def test_metno_parser_fills_with_six_hour_blocks():
    payload = {"properties": {"timeseries": [
        {"time": "t", "data": {"next_6_hours": {"details": {"precipitation_amount": 3.0}}}}
        for _ in range(4)
    ]}}
    # four non-overlapping 6h blocks = 24h
    assert flood._metno_rainfall_24h(payload) == 12.0


def test_metno_parser_rejects_garbage():
    assert flood._metno_rainfall_24h({}) is None
    assert flood._metno_rainfall_24h({"properties": {"timeseries": []}}) is None


def test_provider_off_uses_offline_default():
    flood._rain_cache.update(value=None, at=0.0)
    assert flood.fetch_pagasa_rainfall_mm() == flood.DEFAULT_RAINFALL_MM
    assert "default" in flood.rainfall_source()
