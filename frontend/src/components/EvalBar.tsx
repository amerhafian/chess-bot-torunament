type EvalData = {
  score: number
  white_pct: number
  label: string
}

type Props = {
  evaluation?: EvalData | null
  height: number
  orientation?: 'white' | 'black'
  className?: string
}

/** Vertical eval bar: white advantage from the bottom when orientation is white. */
export function EvalBar({
  evaluation,
  height,
  orientation = 'white',
  className = '',
}: Props) {
  const whitePct = evaluation?.white_pct ?? 50
  const label = evaluation?.label ?? '0.0'
  // Segment from the bottom of the bar = side at the bottom of the board
  const bottomIsWhite = orientation === 'white'
  const bottomPct = bottomIsWhite ? whitePct : 100 - whitePct

  return (
    <div
      className={`relative flex w-7 shrink-0 overflow-hidden rounded-sm shadow-[0_8px_18px_rgba(26,20,16,0.22)] ${className}`}
      style={{ height }}
      title={evaluation ? `Eval ${label} (White perspective)` : 'Eval'}
      aria-label={`Evaluation ${label}`}
    >
      <div className="absolute inset-0 flex flex-col">
        <div
          className="bg-[#1a1410] transition-[flex-grow] duration-300 ease-out"
          style={{ flexGrow: Math.max(0.01, 100 - bottomPct) }}
        />
        <div
          className="bg-[#f3e6d4] transition-[flex-grow] duration-300 ease-out"
          style={{ flexGrow: Math.max(0.01, bottomPct) }}
        />
      </div>
      <div className="absolute inset-x-0 top-1/2 z-10 -translate-y-1/2 text-center">
        <span
          className={`inline-block rounded px-0.5 text-[10px] font-bold leading-none tabular-nums ${
            whitePct >= 50 ? 'bg-[#1a1410]/70 text-[#f3e6d4]' : 'bg-[#f3e6d4]/80 text-[#1a1410]'
          }`}
        >
          {label}
        </span>
      </div>
    </div>
  )
}
