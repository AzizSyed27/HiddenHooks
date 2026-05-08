"use client"

import { useState } from "react"
import { Loader2, MapPin } from "lucide-react"
import { cn } from "@/lib/utils"
import type { NearLocation, RadiusKm } from "@/lib/types"

const RADIUS_OPTIONS: RadiusKm[] = [30, 60, 100]

interface LocationFilterProps {
  nearLocation: NearLocation | null
  radiusKm: RadiusKm | null
  onLocationChange: (loc: NearLocation | null) => void
  onRadiusChange: (radius: RadiusKm) => void
  onClear: () => void
}

export default function LocationFilter({
  nearLocation,
  radiusKm,
  onLocationChange,
  onRadiusChange,
  onClear,
}: LocationFilterProps) {
  const [showSetter, setShowSetter] = useState(false)
  const [geoStatus, setGeoStatus] = useState<"idle" | "loading" | "error">("idle")
  const [geoError, setGeoError] = useState<string | null>(null)
  const [manualLat, setManualLat] = useState("")
  const [manualLon, setManualLon] = useState("")
  const [manualError, setManualError] = useState<string | null>(null)
  const [addressQuery, setAddressQuery] = useState("")
  const [geocoding, setGeocoding] = useState(false)
  const [geocodeError, setGeocodeError] = useState<string | null>(null)

  function handleGeolocate() {
    if (!navigator.geolocation) {
      setGeoError("Geolocation not supported")
      return
    }
    setGeoStatus("loading")
    setGeoError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeoStatus("idle")
        onLocationChange({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        })
        setShowSetter(false)
      },
      () => {
        setGeoStatus("error")
        setGeoError("Location unavailable")
      },
    )
  }

  function handleManualSet() {
    const lat = parseFloat(manualLat)
    const lon = parseFloat(manualLon)
    if (isNaN(lat) || lat < 41 || lat > 50) {
      setManualError("Lat must be 41–50")
      return
    }
    if (isNaN(lon) || lon < -85 || lon > -74) {
      setManualError("Lon must be −85–−74")
      return
    }
    setManualError(null)
    onLocationChange({ lat, lon })
    setShowSetter(false)
  }

  async function handleAddressSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!addressQuery.trim()) return
    setGeocoding(true)
    setGeocodeError(null)
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(addressQuery)}&countrycodes=ca&limit=1`
      const res = await fetch(url)
      const data = (await res.json()) as Array<{ lat: string; lon: string }>
      if (!data.length) {
        setGeocodeError("No results found")
        return
      }
      onLocationChange({ lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) })
      setShowSetter(false)
    } catch {
      setGeocodeError("Search failed")
    } finally {
      setGeocoding(false)
    }
  }

  // State 3: active filter
  if (nearLocation !== null) {
    const accuracyHighlighted = nearLocation.accuracy != null && nearLocation.accuracy > 1000
    const accuracyKm =
      nearLocation.accuracy != null ? Math.round(nearLocation.accuracy / 1000) : null

    return (
      <div className="space-y-2 border-b px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1.5">
            <MapPin size={12} className="shrink-0 text-muted-foreground" />
            <span className="truncate font-sans text-[11px] text-foreground">
              {nearLocation.lat.toFixed(4)}°N, {Math.abs(nearLocation.lon).toFixed(4)}°W
            </span>
            {accuracyKm != null && (
              <span
                className={cn(
                  "shrink-0 font-sans text-[10px]",
                  accuracyHighlighted ? "text-orange-400" : "text-muted-foreground",
                )}
              >
                (±{accuracyKm} km)
              </span>
            )}
          </div>
          <button
            onClick={() => {
              onLocationChange(null)
              setShowSetter(true)
            }}
            className="shrink-0 font-sans text-[10px] text-muted-foreground underline hover:no-underline"
          >
            Change
          </button>
        </div>

        <div className="flex gap-1.5">
          {RADIUS_OPTIONS.map((km) => {
            const active = radiusKm === km
            return (
              <button
                key={km}
                onClick={() => {
                  if (!active) onRadiusChange(km)
                }}
                className={cn(
                  "rounded-full px-3 py-1 font-sans text-xs font-medium transition-colors",
                  active
                    ? "cursor-default bg-foreground text-background"
                    : "bg-muted text-muted-foreground hover:bg-muted/80",
                )}
              >
                {km} km
              </button>
            )
          })}
        </div>

        <div className="text-right">
          <button
            onClick={onClear}
            className="font-sans text-[10px] text-muted-foreground underline hover:no-underline"
          >
            Clear filter
          </button>
        </div>
      </div>
    )
  }

  // State 1: off
  if (!showSetter) {
    return (
      <div className="border-b px-4 py-2.5">
        <button
          onClick={() => setShowSetter(true)}
          className="w-full text-left font-sans text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          ○ Filter by distance from location
        </button>
      </div>
    )
  }

  // State 2: location setter
  return (
    <div className="space-y-3 border-b px-4 py-3">
      <button
        onClick={handleGeolocate}
        disabled={geoStatus === "loading"}
        className="flex w-full items-center gap-2 rounded-md bg-muted px-3 py-2 font-sans text-xs transition-colors hover:bg-muted/80 disabled:opacity-60"
      >
        {geoStatus === "loading" ? (
          <Loader2 size={12} className="animate-spin" />
        ) : (
          <MapPin size={12} />
        )}
        Use my current location
      </button>
      {geoError && (
        <p className="font-sans text-[10px] text-destructive">
          {geoError} — enter coordinates below
        </p>
      )}

      <div className="space-y-1">
        <div className="flex gap-1.5">
          <input
            type="text"
            placeholder="Lat"
            value={manualLat}
            onChange={(e) => {
              setManualLat(e.target.value)
              setManualError(null)
            }}
            className="h-7 flex-1 rounded border border-border bg-background px-2 font-mono text-[11px] focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <input
            type="text"
            placeholder="Lon"
            value={manualLon}
            onChange={(e) => {
              setManualLon(e.target.value)
              setManualError(null)
            }}
            className="h-7 flex-1 rounded border border-border bg-background px-2 font-mono text-[11px] focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <button
            onClick={handleManualSet}
            className="h-7 rounded bg-muted px-2.5 font-sans text-[11px] font-medium hover:bg-muted/80"
          >
            Set
          </button>
        </div>
        {manualError && (
          <p className="font-sans text-[10px] text-destructive">{manualError}</p>
        )}
      </div>

      <form onSubmit={handleAddressSearch} className="space-y-1">
        <div className="flex gap-1.5">
          <input
            type="text"
            placeholder="Search address or place"
            value={addressQuery}
            onChange={(e) => {
              setAddressQuery(e.target.value)
              setGeocodeError(null)
            }}
            className="h-7 flex-1 rounded border border-border bg-background px-2 font-sans text-[11px] focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <button
            type="submit"
            disabled={geocoding}
            className="flex h-7 items-center gap-1.5 rounded bg-muted px-2.5 font-sans text-[11px] font-medium hover:bg-muted/80 disabled:opacity-60"
          >
            {geocoding && <Loader2 size={10} className="animate-spin" />}
            Search
          </button>
        </div>
        {geocodeError && (
          <p className="font-sans text-[10px] text-destructive">{geocodeError}</p>
        )}
      </form>

      <button
        onClick={() => setShowSetter(false)}
        className="font-sans text-[10px] text-muted-foreground underline hover:no-underline"
      >
        Cancel
      </button>
    </div>
  )
}
