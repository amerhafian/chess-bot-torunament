import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, formatWeights, type SavedWeights } from '../api'

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
  const [depth, setDepth] = useState(3)
  const [rangeA, setRangeA] = useState<Range>({ min: 0.5, max: 2.0 })
  const [rangeB, setRangeB] = useState<Range>({ min: 0.0, max: 1.0 })
  const [rangeC, setRangeC] = useState<Range>({ min: 0.0, max: 1.0 })
  const [rangeD, setRangeD] = useState<Range>({ min: 0.0, max: 1.0 })
  const [rangeE, setRangeE] = useState<Range>({ min: 0.0, max: 1.0 })
  const [rangeExp, setRangeExp] = useState<Range>({ min: 0.5, max: 1.5 })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refineError, setRefineError] = useState<string | null>(null)
  const [finding, setFinding] = useState(false)
  const [saved, setSaved] = useState<SavedWeights[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  useEffect(() => {
    api.listWeights().then(setSaved).catch(() => setSaved([]))
  }, [])

  const toggleSaved = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]))
  }

  const findWeights = async () => {
    setRefineError(null)
    setFinding(true)
    try {
      const job = await api.startRefine(botCount, depth, selectedIds)
      if (job.tournament_id) navigate(`/tournament/${job.tournament_id}`)
    } catch (err) {
      setRefineError(err instanceof Error ? err.message : 'Could not start weight search')
      setFinding(false)
    }
  }

  const gameEstimate = useMemo(() => {
    if (format === 'round_robin') return botCount * (botCount - 1)
    return Math.max(0, botCount - 1)
  }, [botCount, format])

  const refineGames = 5 * botCount * (botCount - 1)
  const randomSeats = Math.max(0, botCount - selectedIds.length)
  const tooManySaved = selectedIds.length > botCount
  const noSearchSeat = selectedIds.length >= botCount

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
        range_d: rangeD,
        range_e: rangeE,
        range_exp: rangeExp,
        weight_ids: selectedIds,
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
        Spawn bots with random power-form weights and let them duel. You can also pin saved bots into the field. Unwatched games run at full speed; open any game to watch live (≈1s per move).
        Depth is in plies (depth 4 ≈ M2).
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
            <span className="mb-1 block font-medium">Search depth (plies)</span>
            <input
              type="number"
              min={1}
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

        <div className="panel rounded-xl p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-xl font-semibold text-[var(--color-felt-deep)]">Saved bots</h2>
            <span className="text-xs text-[var(--color-ink-soft)]">
              {selectedIds.length} saved · {randomSeats} random
            </span>
          </div>
          <p className="mt-1 text-sm text-[var(--color-ink-soft)]">
            Checked presets take a seat and keep their name. Begin tournament fills the other seats from the ranges. Find weights keeps the checked bots in every round.
          </p>
          {saved.length === 0 ? (
            <p className="mt-3 text-sm text-[var(--color-ink-soft)]">
              None saved yet.{' '}
              <Link className="underline" to="/weights">
                Add weights
              </Link>
            </p>
          ) : (
            <ul className="mt-3 max-h-56 space-y-2 overflow-y-auto">
              {saved.map((item) => (
                <li key={item.id}>
                  <label className="flex cursor-pointer items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={selectedIds.includes(item.id)}
                      onChange={() => toggleSaved(item.id)}
                    />
                    <span>
                      <span className="font-medium">{item.bot_name || item.name}</span>
                      <span className="mt-0.5 block text-xs text-[var(--color-ink-soft)]">{formatWeights(item)}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          {tooManySaved && (
            <p className="mt-2 text-sm text-rose-700">Raise the bot count, or uncheck a saved bot. The field only has {botCount} seats.</p>
          )}
        </div>

        <RangeFields label="Coeff a1 — material" hint="piece values" value={rangeA} onChange={setRangeA} />
        <RangeFields label="Coeff b1 — controlled squares" hint="attack coverage" value={rangeB} onChange={setRangeB} />
        <RangeFields label="Coeff c1 — king pressure" hint="king ring attackers" value={rangeC} onChange={setRangeC} />
        <RangeFields label="Coeff d1 — attacked pieces" hint="enemy pieces attacked" value={rangeD} onChange={setRangeD} />
        <RangeFields label="Coeff e1 — center control" hint="d4/d5/e4/e5" value={rangeE} onChange={setRangeE} />
        <RangeFields label="Exponent range (all metrics)" hint="power a2…e2" value={rangeExp} onChange={setRangeExp} />

        <div className="panel rounded-xl p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-display text-xl font-semibold text-[var(--color-felt-deep)]">Find weights</h2>
              <p className="mt-1 text-sm text-[var(--color-ink-soft)]">
                Uses the bot count and depth above, and ignores the ranges. Checked saved bots stay in every round; the other seats try coarse weights, then smaller steps around the champion. Material stays at 1. About {refineGames} full games.
              </p>
            </div>
            <button
              type="button"
              disabled={finding || noSearchSeat}
              onClick={findWeights}
              className="rounded-md border border-[rgba(92,58,26,0.35)] bg-white/70 px-4 py-2 text-sm font-semibold disabled:opacity-60"
            >
              {finding ? 'Starting…' : 'Find weights'}
            </button>
          </div>
          {noSearchSeat && (
            <p className="mt-2 text-sm text-rose-700">Leave at least one seat open so the search can try new weights.</p>
          )}
          {refineError && <p className="mt-2 text-sm text-rose-700">{refineError}</p>}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-[var(--color-ink-soft)]">
            ≈ {gameEstimate} games · depth {depth}
            {format === 'single_elimination' && ' · draws rematch then random if needed'}
          </p>
          <button
            type="button"
            disabled={loading || tooManySaved}
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
