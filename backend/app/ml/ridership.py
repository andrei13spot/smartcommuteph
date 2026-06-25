# ridership / crowding predictor (the lstm part).
# the real model will be an lstm trained on hourly ridership. for now this just
# scales each edge's baseline crowding by a time-of-day demand curve so the rest
# of the pipeline runs with static data. same interface: predict(edge, hour) -> 0..1.
from __future__ import annotations

from ..routing.graph import Edge


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# demand factor per hour of day. twin peaks in the am/pm rush, lower off-peak.
_HOURLY_DEMAND = {
    **{h: 0.45 for h in range(0, 5)},
    5: 0.70, 6: 1.05, 7: 1.40, 8: 1.45, 9: 1.20,
    10: 0.95, 11: 0.90, 12: 1.00, 13: 0.95, 14: 0.90,
    15: 0.95, 16: 1.15, 17: 1.45, 18: 1.50, 19: 1.30,
    20: 1.05, 21: 0.85, 22: 0.65, 23: 0.50,
}


class RidershipPredictor:
    name = "lstm-ridership"

    def demand_factor(self, hour: int) -> float:
        return _HOURLY_DEMAND.get(hour % 24, 1.0)

    def predict(self, edge: Edge, hour: int) -> float:
        # crowding for this edge at this hour, 0..1
        return _clamp01(edge.ridership * self.demand_factor(hour))


predictor = RidershipPredictor()
