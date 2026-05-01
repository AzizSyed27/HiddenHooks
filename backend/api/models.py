from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CandidateProperties(BaseModel):
    id: int
    name: str | None
    candidate_type: str
    source_dataset: str
    dist_to_road_meters: float | None
    area_m2: float | None
    length_m: float | None
    rank: int


class CandidateFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict
    properties: CandidateProperties


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[CandidateFeature]
