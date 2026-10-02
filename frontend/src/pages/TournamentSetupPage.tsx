import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

type Range = { min: number; max: number }

function RangeFields({
  label,
  value,
  onChange,
  hint,
}: {
  label: string
  value: Range
  onChange: (v: Range) => void
  hint: string
}) {
  return (
    <div className="panel rounded-xl p-4">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="font-display text-lg font-semibold text-[var(--color-felt-deep)]">{label}</h3>
        <span className="text-xs text-[var(--color-ink-soft)]">{hint}</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-[var(--color-ink-soft)]">Min</span>
          <input
            type="number"
            step="0.1"
            className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
            value={value.min}
            onChange={(e) => onChange({ ...value, min: Number(e.target.value) })}
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-[var(--color-ink-soft)]">Max</span>
          <input
            type="number"
            step="0.1"
            className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
            value={value.max}
            onChange={(e) => onChange({ ...value, max: Number(e.target.value) })}
          />
        </label>
      </div>
    </div>
  )
}

export function TournamentSetupPage() {
  const navigate = useNavigate()
  const [botCount, setBotCount] = useState(4)
  const [format, setFormat] = useState<'round_robin' | 'single_elimination'>('round_robin')
  const [depth, setDepth] = useState(5)
  const [rangeA, setRangeA] = useState<Range>({ min: 0.5, max: 2.0 })
  const [rangeB, setRangeB] = useState<Range>({ min: 0.0, max: 1.0 })
  const [rangeC, setRangeC] = useState<Range>({ min: 0.0, max: 1.0 })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const gameEstimate = useMemo(() => {
    if (format === 'round_robin') return botCount * (botCount - 1)
    return Math.max(0, botCount - 1)
  }, [botCount, format])

  const start = async () => {
    setLoading(true)
    setError(null)
    try {
      const t = await api.createTournament({
        bot_count: botCount,
        format,
        depth,
        range_a: rangeA,
        range_b: rangeB,
        range_c: rangeC,
      })
      navigate(`/tournament/${t.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start tournament')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="font-display text-4xl font-bold text-[var(--color-felt-deep)]">New tournament</h1>
      <p className="mt-2 text-[var(--color-ink-soft)]">
        Spawn bots with random weights and let them duel. Unwatched games run at full speed; open any game to watch live (≈1s per move).
      </p>

      <div className="mt-8 grid gap-4">
        <div className="panel grid gap-4 rounded-xl p-5 sm:grid-cols-3">
          <label className="text-sm">
            <span className="mb-1 block font-medium">Number of bots</span>
            <input
              type="number"
              min={2}
              max={32}
              className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
              value={botCount}
              onChange={(e) => setBotCount(Number(e.target.value))}
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium">Search depth</span>
            <input
              type="number"
              min={1}
              max={6}
              className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
            />
          </label>
          <div className="text-sm">
            <span className="mb-1 block font-medium">Format</span>
            <div className="flex overflow-hidden rounded-md border border-[rgba(92,58,26,0.25)]">
              <button
                type="button"
                className={`flex-1 px-3 py-2 ${format === 'round_robin' ? 'bg-[var(--color-felt)] text-[#f5f0e6]' : 'bg-white/60'}`}
                onClick={() => setFormat('round_robin')}
              >
                Round-robin
              </button>
              <button
                type="button"
                className={`flex-1 px-3 py-2 ${format === 'single_elimination' ? 'bg-[var(--color-felt)] text-[#f5f0e6]' : 'bg-white/60'}`}
                onClick={() => setFormat('single_elimination')}
              >
                Elimination
              </button>
            </div>
          </div>
        </div>

        <RangeFields label="Weight a — material" hint="piece values" value={rangeA} onChange={setRangeA} />
        <RangeFields label="Weight b — controlled squares" hint="attack coverage" value={rangeB} onChange={setRangeB} />
        <RangeFields label="Weight c — checking moves" hint="king pressure" value={rangeC} onChange={setRangeC} />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-[var(--color-ink-soft)]">
            ≈ {gameEstimate} games · depth {depth}
            {format === 'single_elimination' && ' · draws rematch then random if needed'}
          </p>
          <button
            type="button"
            disabled={loading}
            onClick={start}
            className="btn-primary rounded-md px-6 py-2.5 text-sm font-semibold disabled:opacity-60"
          >
            {loading ? 'Starting…' : 'Begin tournament'}
          </button>
        </div>
        {error && <p className="text-sm text-rose-700">{error}</p>}
      </div>
    </div>
  )
}
