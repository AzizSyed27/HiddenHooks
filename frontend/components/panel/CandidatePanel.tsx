"use client"

import { motion, AnimatePresence } from "framer-motion"
import { ChevronLeft } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { SheetHeader } from "@/components/ui/sheet"
import { cn } from "@/lib/utils"
import type { CandidateCollection, CandidateFeature, CandidateProperties } from "@/lib/types"

// Matches the amber→cyan→slate color ramp used in MapView layers.
function rankColorHex(normalizedRank: number): string {
  if (normalizedRank <= 0.4) {
    const t = normalizedRank / 0.4
    return `rgb(${Math.round(245 + (6 - 245) * t)},${Math.round(158 + (182 - 158) * t)},${Math.round(11 + (212 - 11) * t)})`
  }
  const t = (normalizedRank - 0.4) / 0.6
  return `rgb(${Math.round(6 + (51 - 6) * t)},${Math.round(182 + (65 - 182) * t)},${Math.round(212 + (85 - 212) * t)})`
}

function displayName(props: CandidateProperties): string {
  if (props.name && props.name !== "NaN") return props.name
  return props.candidate_type === "polygon" ? "Unnamed pond" : "Unnamed stream reach"
}

interface CandidatePanelProps {
  candidates: CandidateCollection | null
  selectedId: number | null
  onSelect: (id: number | null) => void
  onClose: () => void
}

export default function CandidatePanel({
  candidates,
  selectedId,
  onSelect,
  onClose,
}: CandidatePanelProps) {
  const total = candidates?.features.length ?? 0
  const selectedFeature: CandidateFeature | null =
    selectedId != null
      ? (candidates?.features.find((f) => f.properties.id === selectedId) ?? null)
      : null

  return (
    <motion.div
      initial={{ x: -320 }}
      animate={{ x: 0 }}
      exit={{ x: -320 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="fixed left-0 top-0 z-10 flex h-full w-[320px] flex-col border-r bg-popover shadow-xl"
    >
      {/* Header — SheetHeader provides the flex-col + padding base */}
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

      {/* Detail card — slides in/out when a candidate is selected */}
      <AnimatePresence>
        {selectedFeature && (
          <motion.div
            key={selectedId}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15 }}
            className="border-b bg-muted/30 px-4 pb-4 pt-3"
          >
            <p className="font-serif text-base font-medium leading-snug">
              {displayName(selectedFeature.properties)}
            </p>
            <p className="mt-0.5 font-sans text-xs text-muted-foreground">
              Rank #{selectedFeature.properties.rank} of {total}
              {" · "}
              {selectedFeature.properties.dist_to_road_meters != null
                ? `${selectedFeature.properties.dist_to_road_meters.toFixed(0)} m from road`
                : "—"}
            </p>
            {selectedFeature.properties.candidate_type === "polygon" &&
              selectedFeature.properties.area_m2 != null && (
                <p className="font-sans text-xs text-muted-foreground">
                  {(selectedFeature.properties.area_m2 / 10000).toFixed(2)} ha
                </p>
              )}
            {selectedFeature.properties.candidate_type === "reach_full" &&
              selectedFeature.properties.length_m != null && (
                <p className="font-sans text-xs text-muted-foreground">
                  {(selectedFeature.properties.length_m / 1000).toFixed(2)} km
                </p>
              )}
            {/* Hiddenness bar — single signal for Phase 1 */}
            <div className="mt-3">
              <p className="mb-1 font-sans text-[10px] uppercase tracking-wide text-muted-foreground">
                Hiddenness
              </p>
              <div className="h-1.5 rounded-full bg-muted">
                <div
                  style={{
                    width: `${(1 - selectedFeature.properties.normalizedRank) * 100}%`,
                  }}
                  className="h-full rounded-full bg-amber-400 transition-all duration-300"
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Ranked candidate list */}
      <div className="flex-1 overflow-y-auto">
        {candidates?.features.map((f) => {
          const p = f.properties
          const isSelected = p.id === selectedId
          return (
            <button
              key={p.id}
              onClick={() => onSelect(p.id)}
              className={cn(
                "flex w-full items-center gap-3 border-b border-border/40 px-4 py-2.5 text-left",
                "hover:bg-muted/50",
                isSelected && "bg-muted",
              )}
            >
              <Badge
                style={{ background: rankColorHex(p.normalizedRank), color: "#fff" }}
                className="shrink-0 justify-center border-0 font-sans text-[10px] font-semibold"
              >
                {p.rank}
              </Badge>
              <div className="min-w-0">
                <p className="truncate font-serif text-sm leading-tight">
                  {displayName(p)}
                </p>
                <p className="font-sans text-xs text-muted-foreground">
                  {p.dist_to_road_meters != null
                    ? `${p.dist_to_road_meters.toFixed(0)} m`
                    : "—"}
                </p>
              </div>
            </button>
          )
        })}
      </div>
    </motion.div>
  )
}
