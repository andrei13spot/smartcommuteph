# app settings
from __future__ import annotations

import os

# origins allowed to call the api from the browser. defaults cover the static
# frontend served locally and the usual dev ports.
_DEFAULT_ORIGINS = "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000,*"

CORS_ORIGINS = [o.strip() for o in os.getenv("SCPH_CORS_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]

API_TITLE = "SmartCommute PH - Commuter Routing API"
API_VERSION = "0.1.0"
API_DESCRIPTION = (
    "multi-criteria routing: ahp profile weights + ml-predicted edge values "
    "(lstm ridership, rfr flood risk) inside a constraint-aware a* over the "
    "cubao-quadrant transit graph."
)
