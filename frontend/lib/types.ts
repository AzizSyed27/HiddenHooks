import type { Feature, FeatureCollection, Geometry } from "geojson"

export interface CandidateProperties {
  id: number
  name: string | null
  candidate_type: "polygon" | "reach_full"
  source_dataset: "waterbody" | "watercourse"
  dist_to_road_meters: number | null
  area_m2: number | null
  length_m: number | null
  rank: number
  normalizedRank: number
}

export type CandidateFeature = Feature<Geometry, CandidateProperties>
export type CandidateCollection = FeatureCollection<Geometry, CandidateProperties>
