"use client"

import { useCallback, useMemo, useState } from "react"
import Map, { Source, Layer, MapMouseEvent } from "react-map-gl/mapbox"
import type { MapRef } from "react-map-gl/mapbox"
import type { ExpressionSpecification, FilterSpecification } from "mapbox-gl"
import "mapbox-gl/dist/mapbox-gl.css"
import type { CandidateCollection, DriveTimeData } from "@/lib/types"

const EMPTY_FC: CandidateCollection = { type: "FeatureCollection", features: [], total_count: 0 }

const POLY_FILTER: FilterSpecification = [
  "in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]],
]
const LINE_FILTER: FilterSpecification = [
  "in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]],
]

// composite is 0 (low, weak signal) → 1 (high, strong signal); amber = best spots
const RANK_COLOR: ExpressionSpecification = [
  "interpolate", ["linear"], ["get", "composite"],
  0,   "#334155",
  0.5, "#06b6d4",
  1,   "#f59e0b",
]

interface MapViewProps {
  mapRef: React.RefObject<MapRef | null>
  candidates: CandidateCollection | null
  selectedId: number | null
  onSelect: (id: number | null) => void
  onMapLoad: () => void
  driveTimeData: DriveTimeData | null
}

export default function MapView({
  mapRef,
  candidates,
  selectedId,
  onSelect,
  onMapLoad,
  driveTimeData,
}: MapViewProps) {
  const [hovered, setHovered] = useState(false)

  // Memoize the route GeoJSON so the Source `data` reference is stable
  // until the geometry actually changes. Mapbox treats prop-reference
  // changes as cache misses; this avoids needless layer rebuilds.
  const routeFeature = useMemo(() => {
    if (!driveTimeData?.route_geometry) return null
    return {
      type: "Feature" as const,
      geometry: driveTimeData.route_geometry,
      properties: {},
    }
  }, [driveTimeData?.route_geometry])

  // Same memoization pattern for the drive-time isochrone polygon.
  // Source: candidates.isochrone_polygon, populated by /candidates only
  // when drive_time_min is set; otherwise null. Cleared automatically
  // when the filter clears (next fetch returns null).
  const isochroneFeature = useMemo(() => {
    const poly = candidates?.isochrone_polygon
    if (!poly) return null
    return {
      type: "Feature" as const,
      geometry: poly,
      properties: {},
    }
  }, [candidates?.isochrone_polygon])

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

      {/* Isochrone polygon — translucent fill + light outline, stacked BELOW
          candidates via beforeId="poly-fill" so candidates and the basemap
          stay readable. Sibling layers within one source: fill first
          (renders below), outline second (renders above the fill but still
          below candidates). */}
      {isochroneFeature && (
        <Source id="isochrone" type="geojson" data={isochroneFeature}>
          <Layer
            id="isochrone-fill"
            type="fill"
            beforeId="poly-fill"
            paint={{ "fill-color": "#94a3b8", "fill-opacity": 0.15 }}
          />
          <Layer
            id="isochrone-outline"
            type="line"
            beforeId="poly-fill"
            paint={{ "line-color": "#475569", "line-width": 1, "line-opacity": 0.5 }}
          />
        </Source>
      )}

      {/* Drive route — sibling source so it stacks above candidate layers.
          Not added to interactiveLayerIds; the route is navigational signal,
          not a click target. Unmounting when routeFeature is null clears the
          layer cleanly — matches detail-card state on fetch failure too,
          since failure leaves driveTimeData.route_geometry null. */}
      {routeFeature && (
        <Source id="drive-route" type="geojson" data={routeFeature}>
          <Layer
            id="drive-route-line"
            type="line"
            paint={{
              "line-color": "#2563eb",
              "line-width": 3.5,
              "line-opacity": 0.9,
            }}
          />
        </Source>
      )}
    </Map>
  )
}
