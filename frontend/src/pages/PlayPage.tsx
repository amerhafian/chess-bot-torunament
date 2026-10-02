import { Chess } from 'chess.js'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, formatWeights, type PlaySession, type SavedWeights } from '../api'
import { Board } from '../components/Board'
import { StatusPill } from '../components/Shell'
import { useWebSocket } from '../hooks/useWebSocket'

export function PlayPage() {
  const [params] = useSearchParams()
  const [weights, setWeights] = useState<SavedWeights[]>([])
  const [mode, setMode] = useState<'import' | 'random'>('random')
  const [weightId, setWeightId] = useState(params.get('weight') || '')
  const [humanColor, setHumanColor] = useState<'white' | 'black'>('white')
  const [depth, setDepth] = useState(5)
  const [rangeA, setRangeA] = useState({ min: 0.5, max: 2 })
  const [rangeB, setRangeB] = useState({ min: 0, max: 1 })
  const [rangeC, setRangeC] = useState({ min: 0, max: 1 })
  const [session, setSession] = useState<PlaySession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    api.listWeights().then((list) => {
      setWeights(list)
      if (params.get('weight')) {
        setMode('import')
        setWeightId(params.get('weight') || '')
      }
    })
  }, [params])

  useWebSocket<{ type: string; session?: PlaySession }>(
    session ? `/ws/play/${session.id}` : null,
    useCallback((msg) => {
      if (msg.session) setSession(msg.session)
    }, []),
  )

  const start = async () => {
    setStarting(true)
    setError(null)
    try {
      const body =
        mode === 'import'
          ? { weight_id: weightId, depth, human_color: humanColor }
          : {
              randomize: true,
              depth,
              human_color: humanColor,
              range_a: rangeA,
              range_b: rangeB,
              range_c: rangeC,
            }
      const s = await api.createPlay(body)
      setSession(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start game')
    } finally {
      setStarting(false)
    }
  }

  const onDrop = (source: string, target: string): boolean => {
    if (!session || session.status !== 'active' || session.bot_thinking) return false
    if (session.turn !== session.human_color) return false

    const chess = new Chess(session.fen)
    let moveUci = source + target
    try {
      const move = chess.move({ from: source, to: target, promotion: 'q' })
      if (!move) return false
      moveUci = move.from + move.to + (move.promotion || '')
    } catch {
      return false
    }

    api
      .playMove(session.id, moveUci)
      .then(setSession)
      .catch((e) => setError(e.message))
    return true
  }

  const canDrag = useMemo(() => {
    return Boolean(
      session &&
        session.status === 'active' &&
        !session.bot_thinking &&
        session.turn === session.human_color,
    )
  }, [session])

  if (session) {
    return (
      <div className="mx-auto max-w-4xl">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-display text-3xl font-bold text-[var(--color-felt-deep)]">
              You vs {session.bot_name}
            </h1>
            <p className="mt-1 text-sm text-[var(--color-ink-soft)]">
              {formatWeights(session.weights)} · depth {session.depth} · you play {session.human_color}
            </p>
          </div>
          <div className="flex gap-2">
            <StatusPill status={session.status === 'finished' ? 'finished' : session.bot_thinking ? 'running' : 'active'} />
            <button type="button" className="btn-secondary rounded-md px-3 py-1.5 text-sm" onClick={() => setSession(null)}>
              New game
            </button>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-[auto_1fr]">
          <Board
            fen={session.fen}
            orientation={session.human_color}
            arePiecesDraggable={canDrag}
            onPieceDrop={onDrop}
            boardWidth={380}
          />
          <div className="panel rounded-xl p-4">
            <h2 className="font-display text-xl font-semibold">Moves</h2>
            {session.bot_thinking && (
              <p className="mt-2 text-sm text-[var(--color-accent)]">Bot is thinking…</p>
            )}
            {session.result && (
              <p className="mt-2 text-sm font-semibold text-[var(--color-felt-deep)]">Result: {session.result}</p>
            )}
            {error && <p className="mt-2 text-sm text-rose-700">{error}</p>}
            <ol className="mt-3 max-h-[320px] space-y-1 overflow-auto text-sm">
              {Array.from({ length: Math.ceil(session.moves.length / 2) }, (_, i) => {
                const w = session.moves[i * 2]
                const b = session.moves[i * 2 + 1]
                return (
                  <li key={i} className="tabular-nums">
                    {i + 1}. {w} {b || ''}
                  </li>
                )
              })}
            </ol>
            <p className="mt-4 text-xs text-[var(--color-ink-soft)]">
              Drag pieces to move. Pawns auto-promote to queen.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-display text-4xl font-bold text-[var(--color-felt-deep)]">Play against a bot</h1>
      <p className="mt-2 text-[var(--color-ink-soft)]">
        Import saved weights (e.g. a tournament winner) or randomize a fresh opponent.
      </p>

      <div className="panel mt-8 space-y-5 rounded-xl p-5">
        <div className="flex overflow-hidden rounded-md border border-[rgba(92,58,26,0.25)]">
          <button
            type="button"
            className={`flex-1 px-3 py-2 text-sm ${mode === 'random' ? 'bg-[var(--color-felt)] text-[#f5f0e6]' : 'bg-white/60'}`}
            onClick={() => setMode('random')}
          >
            Randomize
          </button>
          <button
            type="button"
            className={`flex-1 px-3 py-2 text-sm ${mode === 'import' ? 'bg-[var(--color-felt)] text-[#f5f0e6]' : 'bg-white/60'}`}
            onClick={() => setMode('import')}
          >
            Import weights
          </button>
        </div>

        {mode === 'import' ? (
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Saved weights</span>
            <select
              className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
              value={weightId}
              onChange={(e) => setWeightId(e.target.value)}
            >
              <option value="">Select…</option>
              {weights.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} (a={w.a.toFixed(2)}, b={w.b.toFixed(2)}, c={w.c.toFixed(2)})
                </option>
              ))}
            </select>
            {weights.length === 0 && (
              <p className="mt-2 text-xs text-[var(--color-ink-soft)]">
                No saved weights yet. <Link className="underline" to="/tournament">Run a tournament</Link> or{' '}
                <Link className="underline" to="/weights">save some</Link>.
              </p>
            )}
          </label>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            {([
              ['a', rangeA, setRangeA],
              ['b', rangeB, setRangeB],
              ['c', rangeC, setRangeC],
            ] as const).map(([key, val, setVal]) => (
              <div key={key} className="rounded-lg bg-white/50 p-3">
                <p className="mb-2 text-sm font-medium">Weight {key}</p>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    step="0.1"
                    className="w-full rounded border border-[rgba(92,58,26,0.25)] px-2 py-1 text-sm"
                    value={val.min}
                    onChange={(e) => setVal({ ...val, min: Number(e.target.value) })}
                    placeholder="min"
                  />
                  <input
                    type="number"
                    step="0.1"
                    className="w-full rounded border border-[rgba(92,58,26,0.25)] px-2 py-1 text-sm"
                    value={val.max}
                    onChange={(e) => setVal({ ...val, max: Number(e.target.value) })}
                    placeholder="max"
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block font-medium">Your color</span>
            <select
              className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
              value={humanColor}
              onChange={(e) => setHumanColor(e.target.value as 'white' | 'black')}
            >
              <option value="white">White</option>
              <option value="black">Black</option>
            </select>
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
        </div>

        {error && <p className="text-sm text-rose-700">{error}</p>}

        <button
          type="button"
          disabled={starting || (mode === 'import' && !weightId)}
          onClick={start}
          className="btn-primary rounded-md px-5 py-2.5 text-sm font-semibold disabled:opacity-60"
        >
          {starting ? 'Starting…' : 'Start game'}
        </button>
      </div>
    </div>
  )
}
