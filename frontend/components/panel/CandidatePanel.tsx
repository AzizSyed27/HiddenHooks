"use client"

import { motion, AnimatePresence } from "framer-motion"
import { ChevronLeft, Loader2 } from "lucide-react"
import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { SheetHeader } from "@/components/ui/sheet"
import { cn } from "@/lib/utils"
import type {
  CandidateCollection,
  CandidateFeature,
  CandidateProperties,
  DriveTimeData,
  DriveTimeMin,
  NearLocation,
  RerankResponse,
  TripPlanResponse,
  Weights,
} from "@/lib/types"
import AiRerankResult from "./AiRerankResult"
import CandidateDetail, { ConfidenceDot } from "./CandidateDetail"
import LocationFilter from "./LocationFilter"

// Mirrors the MapView RANK_COLOR expression: 0 (low composite) = slate → 1 (high) = amber
function compositeColor(composite: number): string {
  if (composite <= 0.5) {
    const t = composite / 0.5
    return `rgb(${Math.round(51 + (6 - 51) * t)},${Math.round(65 + (182 - 65) * t)},${Math.round(85 + (212 - 85) * t)})`
  }
  const t = (composite - 0.5) / 0.5
  return `rgb(${Math.round(6 + (245 - 6) * t)},${Math.round(182 + (158 - 182) * t)},${Math.round(212 + (11 - 212) * t)})`
}

function displayName(props: CandidateProperties): string {
  if (props.name && props.name !== "NaN") return props.name
  return props.candidate_type === "polygon" ? "Unnamed pond" : "Unnamed stream reach"
}

const WEIGHT_KEYS = ["w_h", "w_a", "w_f", "w_e"] as const
const WEIGHT_LABELS: Record<(typeof WEIGHT_KEYS)[number], string> = {
  w_h: "H",
  w_a: "A",
  w_f: "F",
  w_e: "E",
}

interface CandidatePanelProps {
  candidates: CandidateCollection | null
  selectedId: number | null
  onSelect: (id: number | null) => void
  onClose: () => void
  fmz: "FMZ16" | "FMZ17" | null
  onFmzChange: (fmz: "FMZ16" | "FMZ17" | null) => void
  weights: Weights
  onWeightsChange: (weights: Weights) => void
  nearLocation: NearLocation | null
  driveTimeMin: DriveTimeMin | null
  onLocationChange: (loc: NearLocation | null) => void
  onDriveTimeChange: (minutes: DriveTimeMin) => void
  onClear: () => void
  driveTimeData: DriveTimeData | null
  driveTimeLoading: boolean
  rerankResult: RerankResponse | null
  rerankLoading: boolean
  rerankError: string | null
  onGetAiTake: () => void
  onClearRerank: () => void
  tripPlanResult: TripPlanResponse | null
  tripPlanLoading: boolean
  tripPlanError: string | null
  onPlanTrip: () => void
  onClearTripPlan: () => void
}

const RERANK_STAGES = [
  "Reasoning…",
  "Specialists analyzing…",
  "Peer review…",
  "Synthesizing…",
]

export default function CandidatePanel({
  candidates,
  selectedId,
  onSelect,
  onClose,
  fmz,
  onFmzChange,
  weights,
  onWeightsChange,
  nearLocation,
  driveTimeMin,
  onLocationChange,
  onDriveTimeChange,
  onClear,
  driveTimeData,
  driveTimeLoading,
  rerankResult,
  rerankLoading,
  rerankError,
  onGetAiTake,
  onClearRerank,
  tripPlanResult,
  tripPlanLoading,
  tripPlanError,
  onPlanTrip,
  onClearTripPlan,
}: CandidatePanelProps) {
  const selectedFeature: CandidateFeature | null =
    selectedId != null
      ? (candidates?.features.find((f) => f.properties.id === selectedId) ?? null)
      : null

  const [rerankStageIdx, setRerankStageIdx] = useState(0)
  useEffect(() => {
    if (!rerankLoading) { setRerankStageIdx(0); return }
    const id = setInterval(() => {
      setRerankStageIdx((i) => (i + 1) % RERANK_STAGES.length)
    }, 10_000)
    return () => clearInterval(id)
  }, [rerankLoading])
  const rerankLoadingText = RERANK_STAGES[rerankStageIdx]

  return (
    <motion.div
      initial={{ x: -360 }}
      animate={{ x: 0 }}
      exit={{ x: -360 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="fixed left-0 top-0 z-10 flex h-full w-[360px] flex-col border-r bg-popover shadow-xl"
    >
      {/* Header */}
      <SheetHeader className="flex flex-row items-center justify-between border-b px-4 py-3">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          HiddenHooks
        </h2>
        <button
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-md hover:bg-muted"
          aria-label="Collapse panel"
        >
          <ChevronLeft size={16} />
        </button>
      </SheetHeader>

      {/* Region selector + AI button */}
      <div className="flex items-center gap-1.5 border-b px-4 py-2.5">
        <div className="flex gap-1.5">
          {(["both", "FMZ16", "FMZ17"] as const).map((v) => {
            const active = v === "both" ? fmz === null : fmz === v
            return (
              <button
                key={v}
                onClick={() => {
                  if (v === "both") onFmzChange(null)
                  else onFmzChange(v)
                }}
                className={cn(
                  "rounded-full px-3 py-1 font-sans text-xs font-medium transition-colors",
                  active
                    ? "bg-foreground text-background"
                    : "bg-muted text-muted-foreground hover:bg-muted/80",
                )}
              >
                {v === "both" ? "Both" : v === "FMZ16" ? "FMZ 16" : "FMZ 17"}
              </button>
            )
          })}
        </div>
        <button
          onClick={onGetAiTake}
          disabled={!nearLocation || rerankLoading || !candidates?.features.length}
          title={!nearLocation ? "Set a location to enable AI re-ranking" : undefined}
          className={cn(
            "ml-auto flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1",
            "font-sans text-xs font-medium transition-colors",
            nearLocation && !rerankLoading
              ? "bg-foreground text-background hover:bg-foreground/80"
              : "cursor-default bg-muted text-muted-foreground opacity-50",
          )}
        >
          {rerankLoading ? (
            <>
              <Loader2 size={12} className="animate-spin" />
              {rerankLoadingText}
            </>
          ) : (
            "Get AI take"
          )}
        </button>
      </div>

      {/* Weight sliders */}
      <div className="space-y-2 border-b px-4 py-3">
        {WEIGHT_KEYS.map((key) => (
          <div key={key} className="flex items-center gap-2">
            <span className="w-3 shrink-0 text-right font-sans text-[10px] font-semibold uppercase text-muted-foreground">
              {WEIGHT_LABELS[key]}
            </span>
            <input
              type="range"
              min={0.01}
              max={1}
              step={0.01}
              value={weights[key]}
              onChange={(e) =>
                onWeightsChange({ ...weights, [key]: parseFloat(e.target.value) })
              }
              className="h-1 flex-1 cursor-pointer accent-amber-400"
            />
            <span className="w-8 text-right font-sans text-[10px] tabular-nums text-muted-foreground">
              {weights[key].toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      {/* Drive-time filter */}
      <LocationFilter
        nearLocation={nearLocation}
        driveTimeMin={driveTimeMin}
        onLocationChange={onLocationChange}
        onDriveTimeChange={onDriveTimeChange}
        onClear={onClear}
      />

      {/* Detail card */}
      <AnimatePresence>
        {selectedFeature && (
          <motion.div
            key={selectedId}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15 }}
          >
            <CandidateDetail
              feature={selectedFeature}
              driveTimeMin={driveTimeMin}
              driveTimeData={driveTimeData}
              driveTimeLoading={driveTimeLoading}
              tripPlanResult={tripPlanResult}
              tripPlanLoading={tripPlanLoading}
              tripPlanError={tripPlanError}
              onPlanTrip={onPlanTrip}
              onClearTripPlan={onClearTripPlan}
              nearLocation={nearLocation}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* AI rerank result OR default candidate list */}
      <div className="flex-1 overflow-y-auto">
        {rerankResult ? (
          <AiRerankResult
            result={rerankResult}
            candidates={candidates}
            selectedId={selectedId}
            onSelect={onSelect}
            onBack={onClearRerank}
          />
        ) : rerankError ? (
          <div className="px-4 py-6 text-center">
            <p className="font-sans text-xs text-destructive">{rerankError}</p>
            <button
              onClick={onGetAiTake}
              className="mt-2 font-sans text-xs underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        ) : (
          candidates?.features.map((f) => {
            const p = f.properties
            const isSelected = p.id === selectedId
            return (
              <button
                key={p.id}
                onClick={() => onSelect(p.id)}
                className={cn(
                  "flex w-full items-center gap-2 border-b border-border/40 px-4 py-2.5 text-left",
                  "hover:bg-muted/50",
                  isSelected && "bg-muted",
                )}
              >
                {/* Rank badge — color mirrors map layer */}
                <Badge
                  style={{ background: compositeColor(p.composite), color: "#fff" }}
                  className="shrink-0 justify-center border-0 font-sans text-[10px] font-semibold"
                >
                  {p.rank}
                </Badge>
                {/* FMZ badge */}
                <span className="shrink-0 rounded bg-muted px-1 font-mono text-[9px] text-muted-foreground">
                  {p.fmz_zone.replace("FMZ", "")}
                </span>
                {/* Name + distance + confidence dot */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <p className="truncate font-serif text-sm leading-tight">
                      {displayName(p)}
                    </p>
                    <ConfidenceDot confidence={p.f_confidence} />
                  </div>
                  <p className="font-sans text-xs text-muted-foreground">
                    {p.dist_to_road_meters != null
                      ? `${p.dist_to_road_meters.toFixed(0)} m`
                      : "—"}
                  </p>
                </div>
              </button>
            )
          })
        )}
      </div>
    </motion.div>
  )
}
