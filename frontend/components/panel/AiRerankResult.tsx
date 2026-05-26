"use client"

import { useMemo, useState } from "react"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import type {
  CandidateCollection,
  RerankResponse,
  RerankedCandidate,
} from "@/lib/types"

function AgreementDot({ agreement }: { agreement: RerankedCandidate["specialist_agreement"] }) {
  if (agreement === "high") {
    return <span className="shrink-0 text-[10px] leading-none text-emerald-400" title="High specialist agreement">●</span>
  }
  if (agreement === "medium") {
    return <span className="shrink-0 text-[10px] leading-none text-amber-400" title="Medium specialist agreement">◐</span>
  }
  return <span className="shrink-0 text-[10px] leading-none text-muted-foreground" title="Low specialist agreement">○</span>
}

interface AiRerankResultProps {
  result: RerankResponse
  candidates: CandidateCollection | null
  selectedId: number | null
  onSelect: (id: number | null) => void
  onBack: () => void
}

export default function AiRerankResult({
  result,
  candidates,
  selectedId,
  onSelect,
  onBack,
}: AiRerankResultProps) {
  const [rationaleOpen, setRationaleOpen] = useState(false)

  const candidateMap = useMemo(
    () => new Map(candidates?.features.map((f) => [f.properties.id, f.properties]) ?? []),
    [candidates],
  )

  const { weighting, current_conditions, synthesis_note, ranked_candidates } = result
  const w = weighting

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="border-b px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <p className="font-sans text-xs font-semibold text-foreground">
            AI ranking · {current_conditions}
          </p>
          <button
            onClick={onBack}
            className="shrink-0 font-sans text-[10px] text-muted-foreground underline hover:no-underline"
          >
            ← Back
          </button>
        </div>

        {/* Weighting row */}
        <p className="mt-1 font-sans text-[10px] text-muted-foreground">
          Weather {w.weather_agent.toFixed(2)} · Timing {w.timing_agent.toFixed(2)} · Species {w.species_agent.toFixed(2)}
          {" "}
          <button
            onClick={() => setRationaleOpen((o) => !o)}
            className="text-muted-foreground underline hover:no-underline"
          >
            {rationaleOpen ? "[hide]" : "[show why]"}
          </button>
        </p>

        {rationaleOpen && (
          <p className="mt-1 font-sans text-[10px] italic text-muted-foreground">
            {w.rationale}
          </p>
        )}

        {synthesis_note && (
          <p className="mt-1.5 font-sans text-[10px] italic text-muted-foreground">
            {synthesis_note}
          </p>
        )}
      </div>

      {/* Ranked list */}
      {ranked_candidates.map((rc) => {
        const props = candidateMap.get(rc.candidate_id)
        const name = props
          ? props.name && props.name !== "NaN"
            ? props.name
            : props.candidate_type === "polygon"
              ? "Unnamed pond"
              : "Unnamed stream reach"
          : `Candidate #${rc.candidate_id}`
        const fmzLabel = props?.fmz_zone?.replace("FMZ", "") ?? "?"
        const isSelected = rc.candidate_id === selectedId

        return (
          <button
            key={rc.candidate_id}
            onClick={() => onSelect(rc.candidate_id)}
            className={cn(
              "flex w-full items-start gap-2 border-b border-border/40 px-4 py-2.5 text-left",
              "hover:bg-muted/50",
              isSelected && "bg-muted",
            )}
          >
            {/* Rank badge */}
            <Badge className="mt-0.5 shrink-0 justify-center border-0 bg-foreground/10 font-sans text-[10px] font-semibold text-foreground">
              #{rc.rank}
            </Badge>

            {/* FMZ badge */}
            <span className="mt-0.5 shrink-0 rounded bg-muted px-1 font-mono text-[9px] text-muted-foreground">
              {fmzLabel}
            </span>

            {/* Name + one_line_why + AI score */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <p className="line-clamp-1 font-serif text-sm leading-tight">
                  {name}
                </p>
                <AgreementDot agreement={rc.specialist_agreement} />
              </div>
              <p className="mt-0.5 line-clamp-2 font-sans text-[10px] leading-snug text-muted-foreground">
                {rc.one_line_why}
              </p>
              <p className="mt-0.5 font-sans text-[10px] text-muted-foreground">
                AI score {rc.composite_call.toFixed(2)}
              </p>
            </div>
          </button>
        )
      })}
    </div>
  )
}
