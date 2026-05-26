"use client"

import { ExternalLink, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { CandidateFeature, DriveTimeData, DriveTimeMin, NearLocation, TripPlanResponse } from "@/lib/types"
import TripPlanResult from "./TripPlanResult"

export function ConfidenceDot({ confidence }: { confidence: string | null }) {
  const colors: Record<string, string> = {
    strong: "bg-emerald-400",
    plausible: "bg-amber-400",
    speculative: "bg-muted-foreground/40",
  }
  if (!confidence) return null
  return (
    <span
      className={cn(
        "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
        colors[confidence] ?? "bg-muted-foreground/40",
      )}
      title={confidence}
    />
  )
}

const CONFIDENCE_STYLES: Record<string, string> = {
  strong: "bg-emerald-100 text-emerald-700",
  plausible: "bg-amber-100 text-amber-700",
  speculative: "bg-muted text-muted-foreground",
}

interface ScoreBarProps {
  label: string
  value: number | null
  barClass: string
}

function ScoreBar({ label, value, barClass }: ScoreBarProps) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-3 shrink-0 text-right font-sans text-[10px] font-semibold uppercase text-muted-foreground">
        {label}
      </span>
      <div className="h-[5px] flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all duration-300", barClass)}
          style={{ width: `${(value ?? 0) * 100}%` }}
        />
      </div>
      <span className="w-7 text-right font-sans text-[10px] tabular-nums text-muted-foreground">
        {value != null ? `${Math.round(value * 100)}%` : "—"}
      </span>
    </div>
  )
}

interface CandidateDetailProps {
  feature: CandidateFeature
  driveTimeMin: DriveTimeMin | null
  driveTimeData: DriveTimeData | null
  driveTimeLoading: boolean
  tripPlanResult: TripPlanResponse | null
  tripPlanLoading: boolean
  tripPlanError: string | null
  onPlanTrip: () => void
  onClearTripPlan: () => void
  nearLocation: NearLocation | null
}

export default function CandidateDetail({
  feature,
  driveTimeMin,
  driveTimeData,
  driveTimeLoading,
  tripPlanResult,
  tripPlanLoading,
  tripPlanError,
  onPlanTrip,
  onClearTripPlan,
  nearLocation,
}: CandidateDetailProps) {
  const p = feature.properties

  // Drive-time text. Single-line so layout doesn't shift between states.
  const driveTimeText = (() => {
    if (driveTimeLoading) return "Computing drive time..."
    if (driveTimeData?.error) return driveTimeData.error
    if (
      driveTimeData?.drive_time_min != null &&
      driveTimeData?.drive_distance_km != null
    ) {
      return `Drive: ${Math.round(driveTimeData.drive_time_min)} min (${driveTimeData.drive_distance_km.toFixed(1)} km) from your location`
    }
    return " " // non-breaking space — reserves line height
  })()

  const name =
    p.name && p.name !== "NaN"
      ? p.name
      : p.candidate_type === "polygon"
        ? "Unnamed pond"
        : "Unnamed stream reach"

  const fmzLabel = p.fmz_zone === "FMZ16" ? "FMZ 16" : "FMZ 17"

  return (
    <div className="border-b bg-muted/30 px-4 pb-4 pt-3">
      {/* Name + confidence badge */}
      <div className="flex items-start justify-between gap-2">
        <p className="font-serif text-base font-medium leading-snug">{name}</p>
        {p.f_confidence && (
          <span
            className={cn(
              "shrink-0 rounded-full px-2 py-0.5 font-sans text-[10px] font-medium",
              CONFIDENCE_STYLES[p.f_confidence] ?? "bg-muted text-muted-foreground",
            )}
          >
            {p.f_confidence.charAt(0).toUpperCase() + p.f_confidence.slice(1)}
          </span>
        )}
      </div>

      {/* FMZ + per-region rank */}
      <p className="mt-0.5 font-sans text-xs text-muted-foreground">
        {fmzLabel}
        {" · "}
        Rank #{p.rank.toLocaleString()} of {p.fmz_total.toLocaleString()} in {fmzLabel}
        {driveTimeMin ? ` within ${driveTimeMin} min` : ""}
      </p>

      {/* Drive-time line — only when filter is active. Single-line so
          the loading -> success transition doesn't shift layout below. */}
      {driveTimeMin != null && (
        <p className="mt-0.5 font-sans text-xs italic text-muted-foreground">
          {driveTimeText}
        </p>
      )}

      {/* Size */}
      {p.candidate_type === "polygon" && p.area_m2 != null && (
        <p className="font-sans text-xs text-muted-foreground">
          {(p.area_m2 / 10000).toFixed(2)} ha
        </p>
      )}
      {p.candidate_type !== "polygon" && p.length_m != null && (
        <p className="font-sans text-xs text-muted-foreground">
          {(p.length_m / 1000).toFixed(2)} km
        </p>
      )}

      {/* Score bars / Trip plan result toggle */}
      {tripPlanResult ? (
        <TripPlanResult result={tripPlanResult} onBack={onClearTripPlan} />
      ) : (
        <>
          {/* Score bars */}
          <div className="mt-3 space-y-1.5">
            {/* Composite — slightly taller bar, top position */}
            <div className="flex items-center gap-2">
              <span className="w-3 shrink-0 text-right font-sans text-[10px] font-semibold text-foreground">
                ★
              </span>
              <div className="h-[7px] flex-1 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-amber-400 transition-all duration-300"
                  style={{ width: `${p.composite * 100}%` }}
                />
              </div>
              <span className="w-7 text-right font-sans text-[10px] font-semibold tabular-nums text-foreground">
                {Math.round(p.composite * 100)}%
              </span>
            </div>
            <ScoreBar label="H" value={p.h_score} barClass="bg-amber-400" />
            <ScoreBar label="A" value={p.a_score} barClass="bg-green-400" />
            <ScoreBar label="F" value={p.f_score} barClass="bg-blue-400" />
            <ScoreBar label="E" value={p.e_score} barClass="bg-emerald-400" />
          </div>

          {/* Raw inputs */}
          <div className="mt-3 space-y-0.5">
            {p.dist_to_road_meters != null && (
              <p className="font-sans text-[10px] text-muted-foreground">
                <span className="font-medium text-foreground/70">Road:</span>{" "}
                {p.dist_to_road_meters.toFixed(0)} m
              </p>
            )}
            {p.a_dist_to_trail_m != null && (
              <p className="font-sans text-[10px] text-muted-foreground">
                <span className="font-medium text-foreground/70">Trail:</span>{" "}
                {p.a_dist_to_trail_m.toFixed(0)} m
              </p>
            )}
            {p.a_dist_to_parking_m != null && (
              <p className="font-sans text-[10px] text-muted-foreground">
                <span className="font-medium text-foreground/70">Parking:</span>{" "}
                {p.a_dist_to_parking_m.toFixed(0)} m
              </p>
            )}
            {p.f_species && (
              <p className="font-sans text-[10px] text-muted-foreground">
                <span className="font-medium text-foreground/70">Fish:</span>{" "}
                {p.f_species}
              </p>
            )}
          </div>

          {/* Plan this trip button */}
          <button
            onClick={onPlanTrip}
            disabled={!nearLocation || tripPlanLoading}
            title={!nearLocation ? "Set a location to enable AI trip planning" : undefined}
            className={cn(
              "mt-3 flex w-full items-center justify-center gap-1.5 rounded-md px-3 py-2",
              "font-sans text-xs font-medium transition-colors",
              nearLocation && !tripPlanLoading
                ? "bg-muted text-foreground hover:bg-muted/80"
                : "cursor-default bg-muted/50 text-muted-foreground",
            )}
          >
            {tripPlanLoading ? (
              <>
                <Loader2 size={12} className="animate-spin" />
                Reasoning…
              </>
            ) : (
              "Plan this trip"
            )}
          </button>

          {tripPlanError && (
            <p className="mt-1 font-sans text-[10px] text-destructive">{tripPlanError}</p>
          )}
        </>
      )}

      {/* Directions button — always shown when parking is available, outside the toggle */}
      {driveTimeData?.parking_lat != null && driveTimeData?.parking_lon != null && (
        <a
          href={`https://www.google.com/maps/dir/?api=1&destination=${driveTimeData.parking_lat},${driveTimeData.parking_lon}`}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-md bg-foreground/90 px-3 py-2 font-sans text-xs font-medium text-background transition-colors hover:bg-foreground"
        >
          <ExternalLink size={12} />
          Get directions to parking
        </a>
      )}
    </div>
  )
}
