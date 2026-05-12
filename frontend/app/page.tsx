"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { AnimatePresence } from "framer-motion"
import { ChevronRight } from "lucide-react"
import type { MapRef } from "react-map-gl/mapbox"
import MapView from "@/components/map/MapView"
import CandidatePanel from "@/components/panel/CandidatePanel"
import type { CandidateCollection, Weights, NearLocation, DriveTimeMin, DriveTimeData } from "@/lib/types"

type Bbox = [number, number, number, number]

// Hardcoded for v1 — should be fetched dynamically from GET /regions (once that endpoint
// exposes bboxes) in a future iteration.
const FMZ_BBOXES: Record<string, Bbox> = {
  FMZ16:    [-83.1173, 41.9094, -78.9081, 45.2666],
  FMZ17:    [-79.2382, 43.7945, -77.5475, 44.7833],
  COMBINED: [-83.1173, 41.9094, -77.5475, 45.2666],
}

const DEFAULT_WEIGHTS: Weights = { w_h: 0.25, w_a: 0.25, w_f: 0.25, w_e: 0.25 }

function getBbox(geometry: { coordinates: unknown }): Bbox {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity
  function walk(c: unknown): void {
    if (typeof (c as number[])[0] === "number") {
      const [lng, lat] = c as [number, number]
      if (lng < w) w = lng
      if (lng > e) e = lng
      if (lat < s) s = lat
      if (lat > n) n = lat
    } else {
      ;(c as unknown[]).forEach(walk)
    }
  }
  walk(geometry.coordinates)
  return [w, s, e, n]
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export default function Home() {
  const mapRef = useRef<MapRef>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [candidates, setCandidates] = useState<CandidateCollection | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)
  const [mapReady, setMapReady] = useState(false)
  const [fmz, setFmz] = useState<"FMZ16" | "FMZ17" | null>(null)
  const [weights, setWeights] = useState<Weights>(DEFAULT_WEIGHTS)
  const [nearLocation, setNearLocation] = useState<NearLocation | null>(null)
  const [driveTimeMin, setDriveTimeMin] = useState<DriveTimeMin | null>(null)
  const [driveTimeData, setDriveTimeData] = useState<DriveTimeData | null>(null)
  const [driveTimeLoading, setDriveTimeLoading] = useState(false)
  const driveTimeAbortRef = useRef<AbortController | null>(null)

  const fetchCandidates = useCallback(async (
    currentFmz: "FMZ16" | "FMZ17" | null,
    currentWeights: Weights,
    currentLocation: NearLocation | null,
    currentDriveTimeMin: DriveTimeMin | null,
  ) => {
    setLoading(true)
    setError(null)
    try {
      const qs = new URLSearchParams({
        w_h: currentWeights.w_h.toString(),
        w_a: currentWeights.w_a.toString(),
        w_f: currentWeights.w_f.toString(),
        w_e: currentWeights.w_e.toString(),
      })
      if (currentFmz) qs.set("fmz", currentFmz)
      if (currentLocation && currentDriveTimeMin) {
        qs.set("near_lat", currentLocation.lat.toString())
        qs.set("near_lon", currentLocation.lon.toString())
        qs.set("drive_time_min", currentDriveTimeMin.toString())
      }
      const res = await fetch(`${API_URL}/candidates?${qs}`)
      if (!res.ok) throw new Error(`API error ${res.status}`)
      setCandidates((await res.json()) as CandidateCollection)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load candidates")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCandidates(null, DEFAULT_WEIGHTS, null, null)
  }, [fetchCandidates])

  // Drive-time fetch: lazy, on candidate selection, only when filter is active.
  // Aborts in-flight fetch on selection change so the response that paints is
  // always the response for the currently-selected candidate.
  useEffect(() => {
    if (selectedId == null || nearLocation == null || driveTimeMin == null) {
      setDriveTimeData(null)
      setDriveTimeLoading(false)
      driveTimeAbortRef.current?.abort()
      driveTimeAbortRef.current = null
      return
    }

    driveTimeAbortRef.current?.abort()
    const controller = new AbortController()
    driveTimeAbortRef.current = controller

    setDriveTimeLoading(true)
    setDriveTimeData(null)

    const qs = new URLSearchParams({
      from_lat: nearLocation.lat.toString(),
      from_lon: nearLocation.lon.toString(),
    })

    fetch(`${API_URL}/candidates/${selectedId}/drive-time?${qs}`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        if (controller.signal.aborted) return
        if (!res.ok) {
          const body = await res.json().catch(() => null)
          setDriveTimeData({
            drive_time_min: null,
            drive_distance_km: null,
            route_geometry: null,
            parking_lat: null,
            parking_lon: null,
            error: body?.detail ?? `Failed to load drive time (${res.status})`,
          })
          return
        }
        const data = (await res.json()) as DriveTimeData
        if (controller.signal.aborted) return
        setDriveTimeData(data)
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        if ((err as Error).name === "AbortError") return
        setDriveTimeData({
          drive_time_min: null,
          drive_distance_km: null,
          route_geometry: null,
          parking_lat: null,
          parking_lon: null,
          error: "Failed to load drive time",
        })
      })
      .finally(() => {
        if (controller.signal.aborted) return
        setDriveTimeLoading(false)
      })

    return () => {
      controller.abort()
    }
  }, [selectedId, nearLocation, driveTimeMin])

  // Fit the viewport to the full candidate set once both map and data are ready.
  useEffect(() => {
    if (!candidates || !mapReady || !mapRef.current) return
    const bbox = candidates.features.reduce<Bbox>(
      (acc, f) => {
        const b = getBbox(f.geometry as { coordinates: unknown })
        return [
          Math.min(acc[0], b[0]),
          Math.min(acc[1], b[1]),
          Math.max(acc[2], b[2]),
          Math.max(acc[3], b[3]),
        ]
      },
      [Infinity, Infinity, -Infinity, -Infinity],
    )
    mapRef.current.fitBounds(bbox, { padding: 40, duration: 1200 })
  }, [candidates, mapReady])

  const handleSelect = useCallback(
    (id: number | null) => {
      setSelectedId(id)
      if (!id || !candidates || !mapRef.current) return
      const feature = candidates.features.find((f) => f.properties.id === id)
      if (!feature) return
      const bbox = getBbox(feature.geometry as { coordinates: unknown })
      mapRef.current.fitBounds(bbox, { padding: 80, maxZoom: 15, duration: 700 })
    },
    [candidates],
  )

  const handleFmzChange = useCallback(
    (newFmz: "FMZ16" | "FMZ17" | null) => {
      setFmz(newFmz)
      fetchCandidates(newFmz, weights, nearLocation, driveTimeMin)
      if (!nearLocation || !driveTimeMin) {
        const bbox = newFmz ? FMZ_BBOXES[newFmz] : FMZ_BBOXES.COMBINED
        mapRef.current?.fitBounds(bbox, { padding: 40, duration: 1200 })
      }
    },
    [fetchCandidates, weights, nearLocation, driveTimeMin],
  )

  const handleWeightsChange = useCallback(
    (newWeights: Weights) => {
      setWeights(newWeights)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(
        () => fetchCandidates(fmz, newWeights, nearLocation, driveTimeMin), 300
      )
    },
    [fetchCandidates, fmz, nearLocation, driveTimeMin],
  )

  const handleLocationChange = useCallback(
    (newLoc: NearLocation | null) => {
      setNearLocation(newLoc)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(
        () => fetchCandidates(fmz, weights, newLoc, driveTimeMin), 300
      )
    },
    [fetchCandidates, fmz, weights, driveTimeMin],
  )

  const handleDriveTimeChange = useCallback(
    (newDriveTime: DriveTimeMin) => {
      setDriveTimeMin(newDriveTime)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(
        () => fetchCandidates(fmz, weights, nearLocation, newDriveTime), 300
      )
    },
    [fetchCandidates, fmz, weights, nearLocation],
  )

  const handleClear = useCallback(() => {
    setNearLocation(null)
    setDriveTimeMin(null)
    fetchCandidates(fmz, weights, null, null)
    const bbox = fmz ? FMZ_BBOXES[fmz] : FMZ_BBOXES.COMBINED
    mapRef.current?.fitBounds(bbox, { padding: 40, duration: 1200 })
  }, [fetchCandidates, fmz, weights])

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      {loading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/20">
          <p className="font-sans text-sm text-white">Loading candidates…</p>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/30">
          <div className="rounded-lg bg-popover p-6 shadow-xl">
            <p className="text-sm text-destructive">{error}</p>
            <button
              onClick={() => fetchCandidates(fmz, weights, nearLocation, driveTimeMin)}
              className="mt-3 text-sm underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      <MapView
        mapRef={mapRef}
        candidates={candidates}
        selectedId={selectedId}
        onSelect={handleSelect}
        onMapLoad={() => setMapReady(true)}
      />

      <AnimatePresence>
        {panelOpen && (
          <CandidatePanel
            candidates={candidates}
            selectedId={selectedId}
            onSelect={handleSelect}
            onClose={() => setPanelOpen(false)}
            fmz={fmz}
            onFmzChange={handleFmzChange}
            weights={weights}
            onWeightsChange={handleWeightsChange}
            nearLocation={nearLocation}
            driveTimeMin={driveTimeMin}
            onLocationChange={handleLocationChange}
            onDriveTimeChange={handleDriveTimeChange}
            onClear={handleClear}
            driveTimeData={driveTimeData}
            driveTimeLoading={driveTimeLoading}
          />
        )}
      </AnimatePresence>

      {!panelOpen && (
        <button
          onClick={() => setPanelOpen(true)}
          className="fixed left-4 top-4 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-popover shadow-md hover:bg-muted"
          aria-label="Open panel"
        >
          <ChevronRight size={18} />
        </button>
      )}
    </div>
  )
}
