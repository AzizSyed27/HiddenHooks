"use client"

import { cn } from "@/lib/utils"
import type { TripPlanResponse } from "@/lib/types"

const CALL_STYLES: Record<TripPlanResponse["overall_call"], string> = {
  "go now":             "bg-emerald-50 text-emerald-600",
  "good window coming": "bg-amber-50 text-amber-600",
  "wait":               "bg-orange-50 text-orange-600",
  "skip":               "bg-muted text-muted-foreground",
}

const CONFIDENCE_STYLES: Record<TripPlanResponse["confidence"], string> = {
  high:   "text-emerald-600",
  medium: "text-amber-600",
  low:    "text-muted-foreground",
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-sans text-[9px] uppercase tracking-widest text-muted-foreground">
      {children}
    </p>
  )
}

interface TripPlanResultProps {
  result: TripPlanResponse
  onBack: () => void
}

export default function TripPlanResult({ result, onBack }: TripPlanResultProps) {
  const {
    overall_call,
    confidence,
    best_window,
    expected_species,
    conditions_summary,
    things_to_watch,
    key_risks,
  } = result

  return (
    <div className="space-y-3 px-4 pb-4 pt-3">
      {/* Overall call + confidence */}
      <div className="flex items-center justify-between gap-2">
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 font-sans text-xs font-semibold capitalize",
            CALL_STYLES[overall_call],
          )}
        >
          {overall_call}
        </span>
        <span className={cn("font-sans text-[10px] font-medium", CONFIDENCE_STYLES[confidence])}>
          {confidence.charAt(0).toUpperCase() + confidence.slice(1)} confidence
        </span>
      </div>

      {/* Best window */}
      <div>
        <SectionHeader>Best window</SectionHeader>
        <p className="mt-0.5 font-serif text-sm leading-snug">{best_window}</p>
      </div>

      {/* Active species */}
      {expected_species.length > 0 && (
        <div>
          <SectionHeader>Active species</SectionHeader>
          <div className="mt-0.5 space-y-1">
            {expected_species.map((s, i) => (
              <div key={i}>
                <p className="font-serif text-sm leading-tight">{s.species}</p>
                <p className="font-sans text-[10px] text-muted-foreground">{s.activity_note}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Conditions */}
      <div>
        <SectionHeader>Conditions</SectionHeader>
        <p className="mt-0.5 font-sans text-xs leading-snug text-muted-foreground">
          {conditions_summary}
        </p>
      </div>

      {/* Watch */}
      {things_to_watch.length > 0 && (
        <div>
          <SectionHeader>Watch</SectionHeader>
          <ul className="mt-0.5 space-y-0.5">
            {things_to_watch.map((item, i) => (
              <li key={i} className="font-sans text-xs text-muted-foreground before:mr-1 before:content-['·']">
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Risks */}
      {key_risks.length > 0 && (
        <div>
          <SectionHeader>Risks</SectionHeader>
          <ul className="mt-0.5 space-y-0.5">
            {key_risks.map((item, i) => (
              <li key={i} className="font-sans text-xs text-muted-foreground before:mr-1 before:content-['·']">
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Back */}
      <button
        onClick={onBack}
        className="font-sans text-[10px] text-muted-foreground underline hover:no-underline"
      >
        ← Back to scores
      </button>
    </div>
  )
}
