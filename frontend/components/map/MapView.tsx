"use client"

import { useCallback, useState } from "react"
import Map, { Source, Layer, MapMouseEvent } from "react-map-gl/mapbox"
import type { MapRef } from "react-map-gl/mapbox"
import type { ExpressionSpecification, FilterSpecification } from "mapbox-gl"
import "mapbox-gl/dist/mapbox-gl.css"
import type { CandidateCollection } from "@/lib/types"

const EMPTY_FC: CandidateCollection = { type: "FeatureCollection", features: [] }

const POLY_FILTER: FilterSpecification = [
  "in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]],
]
const LINE_FILTER: FilterSpecification = [
  "in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]],
]

const RANK_COLOR: ExpressionSpecification = [
  "interpolate", ["linear"], ["get", "normalizedRank"],
  0,   "#f59e0b",
  0.4, "#06b6d4",
  1,   "#334155",
]

interface MapViewProps {
  mapRef: React.RefObject<MapRef | null>
  candidates: CandidateCollection | null
  selectedId: number | null
  onSelect: (id: number | null) => void
  onMapLoad: () => void
}

export default function MapView({
  mapRef,
  candidates,
  selectedId,
  onSelect,
  onMapLoad,
}: MapViewProps) {
  const [hovered, setHovered] = useState(false)

  const highlightFilter: FilterSpecification = [
    "==", ["get", "id"], selectedId ?? -1,
  ]

  const handleClick = useCallback(
    (e: MapMouseEvent) => {
      const id = e.features?.[0]?.properties?.id as number | undefined
      onSelect(id ?? null)
    },
    [onSelect],
  )

  const handleMouseMove = useCallback((e: MapMouseEvent) => {
    setHovered((e.features?.length ?? 0) > 0)
  }, [])

  return (
    <Map
      ref={mapRef}
      mapboxAccessToken={process.env.NEXT_PUBLIC_MAPBOX_TOKEN}
      mapStyle={process.env.NEXT_PUBLIC_MAPBOX_STYLE}
      initialViewState={{ longitude: -79.11, latitude: 43.82, zoom: 11 }}
      style={{ width: "100%", height: "100%" }}
      interactiveLayerIds={["poly-fill", "reach-lines"]}
      onLoad={onMapLoad}
      onClick={handleClick}
      onMouseMove={handleMouseMove}
      cursor={hovered ? "pointer" : "default"}
    >
      <Source id="candidates" type="geojson" data={candidates ?? EMPTY_FC}>
        <Layer
          id="poly-fill"
          type="fill"
          filter={POLY_FILTER}
          paint={{ "fill-color": RANK_COLOR, "fill-opacity": 0.35 }}
        />
        <Layer
          id="poly-outline"
          type="line"
          filter={POLY_FILTER}
          paint={{ "line-color": RANK_COLOR, "line-width": 1 }}
        />
        <Layer
          id="reach-lines"
          type="line"
          filter={LINE_FILTER}
          paint={{ "line-color": RANK_COLOR, "line-width": 2.5 }}
        />
        <Layer
          id="highlight"
          type="line"
          filter={highlightFilter}
          paint={{ "line-color": "#ffffff", "line-width": 2.5, "line-opacity": 0.9 }}
        />
      </Source>
    </Map>
  )
}
