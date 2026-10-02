type Props = {
  ply: number
  total: number
  isLive: boolean
  canPrev: boolean
  canNext: boolean
  onStart: () => void
  onPrev: () => void
  onNext: () => void
  onLive: () => void
}

export function MoveControls({
  ply,
  total,
  isLive,
  canPrev,
  canNext,
  onStart,
  onPrev,
  onNext,
  onLive,
}: Props) {
  const btn =
    'rounded-md border border-[rgba(92,58,26,0.3)] bg-white/70 px-2.5 py-1.5 text-sm font-semibold transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-40'

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" className={btn} onClick={onStart} disabled={!canPrev} title="Start (Home)">
        ⏮
      </button>
      <button type="button" className={btn} onClick={onPrev} disabled={!canPrev} title="Back (←)">
        ◀
      </button>
      <button type="button" className={btn} onClick={onNext} disabled={!canNext} title="Forward (→)">
        ▶
      </button>
      <button type="button" className={btn} onClick={onLive} disabled={isLive} title="Live (End)">
        ⏭ Live
      </button>
      <span className="text-xs text-[var(--color-ink-soft)] tabular-nums">
        {isLive ? 'Live' : `Ply ${ply}`} / {total}
        {!isLive && ' · reviewing'}
      </span>
    </div>
  )
}
