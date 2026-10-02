type Props = {
  moves: string[]
  ply: number
  onSelectPly: (ply: number) => void
  className?: string
}

/** Clickable SAN move list; ply is half-move index after the clicked move. */
export function MoveList({ moves, ply, onSelectPly, className = '' }: Props) {
  if (moves.length === 0) {
    return <p className={`text-sm text-[var(--color-ink-soft)] ${className}`}>No moves yet</p>
  }

  return (
    <ol className={`space-y-0.5 text-sm ${className}`}>
      {Array.from({ length: Math.ceil(moves.length / 2) }, (_, i) => {
        const wIdx = i * 2
        const bIdx = i * 2 + 1
        const w = moves[wIdx]
        const b = moves[bIdx]
        return (
          <li key={i} className="flex gap-1 tabular-nums">
            <span className="w-6 shrink-0 text-[var(--color-ink-soft)]">{i + 1}.</span>
            <MoveButton
              san={w}
              active={ply === wIdx + 1}
              onClick={() => onSelectPly(wIdx + 1)}
            />
            {b && (
              <MoveButton
                san={b}
                active={ply === bIdx + 1}
                onClick={() => onSelectPly(bIdx + 1)}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function MoveButton({
  san,
  active,
  onClick,
}: {
  san: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`min-w-[3.25rem] rounded px-1.5 py-0.5 text-left transition-colors ${
        active
          ? 'bg-[var(--color-felt)] font-semibold text-[#f5f0e6]'
          : 'hover:bg-[rgba(139,90,43,0.12)]'
      }`}
    >
      {san}
    </button>
  )
}
