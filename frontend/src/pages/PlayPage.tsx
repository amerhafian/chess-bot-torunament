import { Chess } from 'chess.js'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, formatWeights, type PlaySession, type SavedWeights } from '../api'
import { Board } from '../components/Board'
import { EvalBar } from '../components/EvalBar'
import { MoveControls } from '../components/MoveControls'
import { MoveList } from '../components/MoveList'
import { StatusPill } from '../components/Shell'
import { useGameReview } from '../hooks/useGameReview'
import { useReviewEvaluation } from '../hooks/useReviewEvaluation'
import { useWebSocket } from '../hooks/useWebSocket'

function PlaySessionView({
  session,
  error,
  canDrag,
  onDrop,
  onNewGame,
}: {
  session: PlaySession
  error: string | null
  canDrag: boolean
  onDrop: (source: string, target: string) => boolean
  onNewGame: () => void
}) {
  const isSf = session.mode === 'stockfish'
  const review = useGameReview(session.moves, session.fen)
  const evaluation = useReviewEvaluation(
    review.isLive,
    session.evaluation,
    review.displayFen,
    review.ply,
    session.eval_history,
    session.weights,
  )
  const sfEvaluation = useReviewEvaluation(
    review.isLive,
    session.sf_evaluation ?? undefined,
    review.displayFen,
    review.ply,
    session.sf_eval_history,
    session.weights,
  )
  const orientation = isSf
    ? session.bot_color || 'white'
    : session.human_color

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-bold text-[var(--color-felt-deep)]">
            {isSf
              ? `${session.bot_name} vs Stockfish`
              : `You vs ${session.bot_name}`}
          </h1>
          <p className="mt-1 text-sm text-[var(--color-ink-soft)]">
            {formatWeights(session.weights)} · bot depth {session.depth}
            {isSf
              ? ` · SF depth ${session.stockfish_depth ?? 14} · Stockfish plays ${session.stockfish_color}`
              : ` · you play ${session.human_color}`}
          </p>
          <p className="mt-1 text-xs text-[var(--color-ink-soft)]">
            Depth is in plies (depth 4 ≈ M2; M4 needs ~7–8 plies).
          </p>
        </div>
        <div className="flex gap-2">
          <StatusPill
            status={
              session.status === 'finished'
                ? 'finished'
                : session.bot_thinking || session.sf_thinking
                  ? 'running'
                  : 'active'
            }
          />
          <button type="button" className="btn-secondary rounded-md px-3 py-1.5 text-sm" onClick={onNewGame}>
            New game
          </button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-[auto_1fr]">
        <div className="space-y-3">
          <div className="flex items-stretch gap-2">
            <div className="flex flex-col items-center gap-1">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-soft)]">
                Bot
              </span>
              <EvalBar evaluation={evaluation} height={380} orientation={orientation} />
            </div>
            {isSf && (
              <div className="flex flex-col items-center gap-1">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-soft)]">
                  SF
                </span>
                <EvalBar evaluation={sfEvaluation} height={380} orientation={orientation} />
              </div>
            )}
            <Board
              fen={review.displayFen}
              orientation={orientation}
              arePiecesDraggable={canDrag && review.isLive && !isSf}
              onPieceDrop={onDrop}
              boardWidth={380}
            />
          </div>
          <MoveControls
            ply={review.ply}
            total={session.moves.length}
            isLive={review.isLive}
            canPrev={review.canPrev}
            canNext={review.canNext}
            onStart={review.goStart}
            onPrev={review.goPrev}
            onNext={review.goNext}
            onLive={review.goLive}
          />
        </div>
        <div className="panel rounded-xl p-4">
          <h2 className="font-display text-xl font-semibold">Moves</h2>
          {(session.bot_thinking || session.sf_thinking) && review.isLive && (
            <p className="mt-2 text-sm text-[var(--color-accent)]">
              {session.sf_thinking ? 'Stockfish is thinking…' : 'Bot is thinking…'}
            </p>
          )}
          {session.result && (
            <p className="mt-2 text-sm font-semibold text-[var(--color-felt-deep)]">
              Result: {session.result}
            </p>
          )}
          {error && <p className="mt-2 text-sm text-rose-700">{error}</p>}
          <MoveList
            moves={session.moves}
            ply={review.ply}
            onSelectPly={review.goToPly}
            className="mt-3 max-h-[280px] overflow-auto"
          />
          <p className="mt-4 text-xs text-[var(--color-ink-soft)]">
            {isSf
              ? 'Auto-play match. ← → scrub history; click a move to jump.'
              : 'Drag pieces to move (live only). ← → scrub history; click a move to jump.'}
          </p>
        </div>
      </div>
    </div>
  )
}

export function PlayPage() {
  const [params] = useSearchParams()
  const [weights, setWeights] = useState<SavedWeights[]>([])
  const [mode, setMode] = useState<'import' | 'random'>('random')
  const [playMode, setPlayMode] = useState<'human' | 'stockfish'>('human')
  const [weightId, setWeightId] = useState(params.get('weight') || '')
  const [humanColor, setHumanColor] = useState<'white' | 'black'>('white')
  const [stockfishColor, setStockfishColor] = useState<'white' | 'black'>('white')
  const [depth, setDepth] = useState(3)
  const [sfDepth, setSfDepth] = useState(14)
  const [sfAvailable, setSfAvailable] = useState<boolean | null>(null)
  const [rangeA, setRangeA] = useState({ min: 0.5, max: 2 })
  const [rangeB, setRangeB] = useState({ min: 0, max: 1 })
  const [rangeC, setRangeC] = useState({ min: 0, max: 1 })
  const [rangeD, setRangeD] = useState({ min: 0, max: 1 })
  const [rangeE, setRangeE] = useState({ min: 0, max: 1 })
  const [rangeExp, setRangeExp] = useState({ min: 0.5, max: 1.5 })
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
    api.stockfishStatus().then((s) => setSfAvailable(s.available)).catch(() => setSfAvailable(false))
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
      const base =
        mode === 'import'
          ? { weight_id: weightId, depth }
          : {
              randomize: true,
              depth,
              range_a: rangeA,
              range_b: rangeB,
              range_c: rangeC,
              range_d: rangeD,
              range_e: rangeE,
              range_exp: rangeExp,
            }
      const body =
        playMode === 'stockfish'
          ? {
              ...base,
              mode: 'stockfish',
              stockfish_color: stockfishColor,
              stockfish_depth: sfDepth,
            }
          : {
              ...base,
              mode: 'human',
              human_color: humanColor,
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
    if (session.mode === 'stockfish') return false
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
        session.mode !== 'stockfish' &&
        session.status === 'active' &&
        !session.bot_thinking &&
        session.turn === session.human_color,
    )
  }, [session])

  if (session) {
    return (
      <PlaySessionView
        session={session}
        error={error}
        canDrag={canDrag}
        onDrop={onDrop}
        onNewGame={() => setSession(null)}
      />
    )
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-display text-4xl font-bold text-[var(--color-felt-deep)]">Play</h1>
      <p className="mt-2 text-[var(--color-ink-soft)]">
        Human vs bot, or watch a weighted bot face Stockfish. Depth is in plies (depth 4 ≈ M2).
      </p>

      <div className="panel mt-8 space-y-5 rounded-xl p-5">
        <div className="flex overflow-hidden rounded-md border border-[rgba(92,58,26,0.25)]">
          <button
            type="button"
            className={`flex-1 px-3 py-2 text-sm ${playMode === 'human' ? 'bg-[var(--color-felt)] text-[#f5f0e6]' : 'bg-white/60'}`}
            onClick={() => setPlayMode('human')}
          >
            You vs bot
          </button>
          <button
            type="button"
            className={`flex-1 px-3 py-2 text-sm ${playMode === 'stockfish' ? 'bg-[var(--color-felt)] text-[#f5f0e6]' : 'bg-white/60'}`}
            onClick={() => setPlayMode('stockfish')}
          >
            Bot vs Stockfish
          </button>
        </div>

        {playMode === 'stockfish' && sfAvailable === false && (
          <p className="text-sm text-rose-700">
            Stockfish binary not found on this server. Install <code>stockfish</code> or set{' '}
            <code>STOCKFISH_PATH</code>.
          </p>
        )}

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
                  {w.name} ({formatWeights(w)})
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
            {(
              [
                ['a1', rangeA, setRangeA],
                ['b1', rangeB, setRangeB],
                ['c1', rangeC, setRangeC],
                ['d1', rangeD, setRangeD],
                ['e1', rangeE, setRangeE],
                ['exp', rangeExp, setRangeExp],
              ] as const
            ).map(([key, val, setVal]) => (
              <div key={key} className="rounded-lg bg-white/50 p-3">
                <p className="mb-2 text-sm font-medium">
                  {key === 'exp' ? 'Exponent range' : `Coeff ${key}`}
                </p>
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
          {playMode === 'human' ? (
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
          ) : (
            <label className="text-sm">
              <span className="mb-1 block font-medium">Stockfish color</span>
              <select
                className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
                value={stockfishColor}
                onChange={(e) => setStockfishColor(e.target.value as 'white' | 'black')}
              >
                <option value="white">White</option>
                <option value="black">Black</option>
              </select>
            </label>
          )}
          <label className="text-sm">
            <span className="mb-1 block font-medium">Bot search depth (plies)</span>
            <input
              type="number"
              min={1}
              className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
            />
          </label>
          {playMode === 'stockfish' && (
            <label className="text-sm sm:col-span-2">
              <span className="mb-1 block font-medium">Stockfish depth</span>
              <input
              type="number"
              min={1}
              className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
              value={sfDepth}
                onChange={(e) => setSfDepth(Number(e.target.value))}
              />
            </label>
          )}
        </div>

        {error && <p className="text-sm text-rose-700">{error}</p>}

        <button
          type="button"
          disabled={
            starting ||
            (mode === 'import' && !weightId) ||
            (playMode === 'stockfish' && sfAvailable === false)
          }
          onClick={start}
          className="btn-primary rounded-md px-5 py-2.5 text-sm font-semibold disabled:opacity-60"
        >
          {starting ? 'Starting…' : 'Start game'}
        </button>
      </div>
    </div>
  )
}
