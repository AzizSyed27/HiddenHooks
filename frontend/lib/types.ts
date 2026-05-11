import type { Feature, FeatureCollection, Geometry } from "geojson"

export interface NearLocation {
  lat: number
  lon: number
  accuracy?: number  // metres, from browser geolocation only
}

export type DriveTimeMin = 20 | 30 | 45 | 60

export interface Weights {
  w_h: number
  w_a: number
  w_f: number
  w_e: number
}

export interface CandidateProperties {
  id: number
  name: string | null
  candidate_type: "polygon" | "reach_full" | "reach_segment"
  source_dataset: string
  fmz_zone: "FMZ16" | "FMZ17"
  dist_to_road_meters: number | null
  area_m2: number | null
  length_m: number | null
  h_score: number | null
  a_score: number | null
  f_score: number | null
  e_score: number | null
  f_confidence: "strong" | "plausible" | "speculative" | null
  f_species: string | null
  a_dist_to_trail_m: number | null
  a_dist_to_parking_m: number | null
  composite: number
  rank: number
  fmz_total: number
}

export type CandidateFeature = Feature<Geometry, CandidateProperties>

// Extends FeatureCollection so it is accepted as GeoJSON.GeoJSON by react-map-gl Source.
// total_count is the pre-LIMIT count from the API — compare with features.length to detect truncation.
export interface CandidateCollection
  extends FeatureCollection<Geometry, CandidateProperties> {
  total_count: number
}
