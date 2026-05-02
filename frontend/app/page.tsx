"use client"

import { useState, useEffect, useMemo, useRef, useCallback } from "react"
import { AnimatePresence } from "framer-motion"
import { ChevronRight } from "lucide-react"
import type { MapRef } from "react-map-gl/mapbox"
import MapView from "@/components/map/MapView"
import CandidatePanel from "@/components/panel/CandidatePanel"
import type { CandidateCollection } from "@/lib/types"
import type { FeatureCollection } from "geojson"

type Bbox = [number, number, number, number]

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
  const [rawCandidates, setRawCandidates] = useState<FeatureCollection | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)
  const [mapReady, setMapReady] = useState(false)

  const fetchCandidates = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_URL}/candidates`)
      if (!res.ok) throw new Error(`API error ${res.status}`)
      setRawCandidates((await res.json()) as FeatureCollection)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load candidates")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCandidates()
  }, [fetchCandidates])

  // Add normalizedRank to each feature; memoized so the GeoJSON reference is
  // stable and react-map-gl won't re-upload unchanged data to the GPU.
  const candidates = useMemo<CandidateCollection | null>(() => {
    if (!rawCandidates) return null
    const n = rawCandidates.features.length
    return {
      ...rawCandidates,
      features: rawCandidates.features.map((f) => ({
        ...f,
        properties: {
          ...(f.properties as object),
          normalizedRank:
            (((f.properties as { rank: number }).rank ?? 1) - 1) /
            Math.max(n - 1, 1),
        },
      })),
    } as CandidateCollection
  }, [rawCandidates])

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
              onClick={fetchCandidates}
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
