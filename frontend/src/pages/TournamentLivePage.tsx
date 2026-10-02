import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, formatWeights, type Game, type RefineJob, type Tournament } from '../api'
import { Board } from '../components/Board'
import { EvalBar } from '../components/EvalBar'
import { MoveControls } from '../components/MoveControls'
import { MoveList } from '../components/MoveList'
import { StatusPill } from '../components/Shell'
import { useGameReview } from '../hooks/useGameReview'
import { useReviewEvaluation } from '../hooks/useReviewEvaluation'
import { useWebSocket } from '../hooks/useWebSocket'

export function TournamentLivePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [tournament, setTournament] = useState<Tournament | null>(null)
  const [refine, setRefine] = useState<RefineJob | null>(null)
  const [watched, setWatched] = useState<string[]>([])
  const [gameMap, setGameMap] = useState<Record<string, Game>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    api
      .getTournament(id)
      .then((t) => {
        setTournament(t)
        const map: Record<string, Game> = {}
        for (const g of t.games) map[g.id] = g
        setGameMap(map)
      })
      .catch((e) => setError(e.message))
  }, [id])

  useEffect(() => {
    let timer: number | undefined
    let cancelled = false
    const tick = () => {
      api
        .refineStatus()
        .then((job) => {
          if (cancelled) return
          setRefine(job)
          if (
            job.status === 'running' &&
            job.tournament_id &&
            id &&
            job.tournament_id !== id &&
            job.tournament_ids?.includes(id)
          ) {
            navigate(`/tournament/${job.tournament_id}`)
          }
          if (job.status === 'running') timer = window.setTimeout(tick, 2000)
        })
        .catch(() => undefined)
    }
    tick()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [id, navigate])

  useWebSocket<{ type: string; tournament?: Tournament; game?: Game }>(
    id ? `/ws/tournaments/${id}` : null,
    useCallback((msg) => {
      if (msg.type === 'tournament' && msg.tournament) {
        setTournament(msg.tournament)
        setGameMap((prev) => {
          const next = { ...prev }
          for (const g of msg.tournament!.games) next[g.id] = g
          return next
        })
      }
      if (msg.type === 'game_update' && msg.game) {
        setGameMap((prev) => ({ ...prev, [msg.game!.id]: msg.game! }))
        setTournament((prev) => {
          if (!prev) return prev
          const games = prev.games.map((g) => (g.id === msg.game!.id ? msg.game! : g))
          if (!games.find((g) => g.id === msg.game!.id)) games.push(msg.game!)
          return { ...prev, games }
        })
      }
    }, []),
  )

  const botsById = useMemo(() => {
    const m: Record<string, string> = {}
    for (const b of tournament?.bots || []) m[b.id] = b.name
    return m
  }, [tournament])

  const games = useMemo(() => {
    const rank = (status: Game['status']) => (status === 'running' ? 0 : status === 'pending' ? 2 : 1)
    return Object.values(gameMap).sort((a, b) => rank(a.status) - rank(b.status) || a.id.localeCompare(b.id))
  }, [gameMap])

  const toggleWatch = (gameId: string) => {
    setWatched((prev) => (prev.includes(gameId) ? prev.filter((id) => id !== gameId) : [...prev, gameId]))
  }

  const saveWinner = async () => {
    if (!tournament?.winner_bot_id) return
    setSaving(true)
    setSaveMsg(null)
    try {
      const saved = await api.saveWinner(tournament.id)
      setSaveMsg(`Saved weights as “${saved.name}”`)
    } catch (e) {
      setSaveMsg(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (error) {
    return <p className="text-rose-700">{error}</p>
  }
  if (!tournament) {
    return <p className="text-[var(--color-ink-soft)]">Loading tournament…</p>
  }

  const winner = tournament.bots.find((b) => b.id === tournament.winner_bot_id)

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-3xl font-bold text-[var(--color-felt-deep)] sm:text-4xl">
              Tournament
            </h1>
            <StatusPill status={tournament.status} />
          </div>
          <p className="mt-2 text-sm text-[var(--color-ink-soft)]">
            {tournament.config.format === 'round_robin' ? 'Round-robin' : 'Single elimination'} ·{' '}
            {tournament.bots.length} bots · depth {tournament.config.depth}
          </p>
          {refine && refine.tournament_ids?.includes(tournament.id) && (
            <p className="mt-1 text-sm text-[var(--color-felt-deep)]">
              Find weights · generation {refine.generation ?? 1} of {refine.generations ?? 5}
              {refine.phase === 'coarse' ? ' · coarse field' : ''}
              {refine.step != null ? ` · step ${refine.step}` : ''}
              {refine.leader ? ` · leader ${refine.leader}` : ''}
              {refine.status === 'finished' ? ' · saved to the library' : ''}
              {refine.status === 'error' ? ` · ${refine.error ?? 'failed'}` : ''}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/tournament" className="btn-secondary rounded-md px-4 py-2 text-sm font-semibold">
            New tournament
          </Link>
          {tournament.status === 'finished' && winner && (
            <button
              type="button"
              disabled={saving}
              onClick={saveWinner}
              className="btn-primary rounded-md px-4 py-2 text-sm font-semibold disabled:opacity-60"
            >
              Save winner weights
            </button>
          )}
        </div>
      </div>

      {saveMsg && <p className="text-sm text-[var(--color-felt-deep)]">{saveMsg}</p>}

      {winner && tournament.status === 'finished' && (
        <div className="panel rounded-xl p-5">
          <p className="text-sm uppercase tracking-wide text-[var(--color-accent)]">Champion</p>
          <h2 className="font-display text-2xl font-semibold text-[var(--color-felt-deep)]">{winner.name}</h2>
          <p className="mt-1 text-sm text-[var(--color-ink-soft)]">{formatWeights(winner.weights)}</p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <aside className="space-y-4">
          {tournament.config.format === 'round_robin' ? (
            <div className="panel rounded-xl p-4">
              <h2 className="font-display text-xl font-semibold">Standings</h2>
              <ol className="mt-3 space-y-2">
                {tournament.standings.map((s, i) => (
                  <li key={s.bot_id} className="flex items-center justify-between gap-2 text-sm">
                    <span>
                      <span className="mr-2 text-[var(--color-ink-soft)]">{i + 1}.</span>
                      {s.name}
                    </span>
                    <span className="font-semibold tabular-nums">{s.points.toFixed(1)}</span>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <div className="panel rounded-xl p-4">
              <h2 className="font-display text-xl font-semibold">Bracket</h2>
              <div className="mt-3 space-y-3">
                {[...new Set(tournament.bracket.map((m) => m.round_index))]
                  .sort((a, b) => a - b)
                  .map((round) => (
                    <div key={round}>
                      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-soft)]">
                        Round {round + 1}
                      </p>
                      <ul className="space-y-1.5">
                        {tournament.bracket
                          .filter((m) => m.round_index === round)
                          .map((m) => (
                            <li key={m.id} className="rounded-md bg-white/50 px-2 py-1.5 text-sm">
                              {m.is_bye ? (
                                <span>Bye → {botsById[m.winner_id || ''] || '—'}</span>
                              ) : (
                                <span>
                                  {botsById[m.bot_a_id || ''] || 'TBD'} vs {botsById[m.bot_b_id || ''] || 'TBD'}
                                  {m.winner_id ? ` → ${botsById[m.winner_id]}` : ''}
                                </span>
                              )}
                            </li>
                          ))}
                      </ul>
                    </div>
                  ))}
              </div>
            </div>
          )}

          <div className="panel rounded-xl p-4">
            <h2 className="font-display text-xl font-semibold">Bots</h2>
            <ul className="mt-3 max-h-64 space-y-2 overflow-auto text-sm">
              {tournament.bots.map((b) => (
                <li key={b.id}>
                  <p className="font-medium">{b.name}</p>
                  <p className="text-xs text-[var(--color-ink-soft)]">{formatWeights(b.weights)}</p>
                </li>
              ))}
            </ul>
          </div>
        </aside>

        <section className="space-y-4">
          {watched.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2">
              {watched.map((gid) => (
                <WatchPanel key={gid} gameId={gid} fallback={gameMap[gid]} onClose={() => toggleWatch(gid)} />
              ))}
            </div>
          )}

          <div className="panel rounded-xl p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h2 className="font-display text-xl font-semibold">Games</h2>
              <p className="text-xs text-[var(--color-ink-soft)]">Click to watch · multi-select OK</p>
            </div>
            <ul className="divide-y divide-[rgba(92,58,26,0.12)]">
              {games.map((g) => {
                const active = watched.includes(g.id)
                return (
                  <li key={g.id}>
                    <button
                      type="button"
                      onClick={() => toggleWatch(g.id)}
                      className={`flex w-full items-center justify-between gap-3 px-2 py-3 text-left transition-colors ${
                        active ? 'bg-[rgba(31,77,58,0.1)]' : 'hover:bg-white/40'
                      }`}
                    >
                      <div>
                        <p className="text-sm font-medium">
                          {g.white.name} <span className="text-[var(--color-ink-soft)]">vs</span> {g.black.name}
                        </p>
                        <p className="text-xs text-[var(--color-ink-soft)]">
                          {g.moves.length} moves
                          {g.result ? ` · ${g.result}` : ''}
                          {g.watchers > 0 ? ` · ${g.watchers} watching` : ''}
                        </p>
                      </div>
                      <StatusPill status={g.status} />
                    </button>
                  </li>
                )
              })}
              {games.length === 0 && <li className="py-6 text-center text-sm text-[var(--color-ink-soft)]">No games yet</li>}
            </ul>
          </div>
        </section>
      </div>
    </div>
  )
}

function WatchPanel({
  gameId,
  fallback,
  onClose,
}: {
  gameId: string
  fallback?: Game
  onClose: () => void
}) {
  const [game, setGame] = useState<Game | null>(fallback || null)

  useEffect(() => {
    if (fallback) {
      setGame(fallback)
      return
    }
    api.getGame(gameId).then(setGame).catch(() => undefined)
  }, [gameId, fallback])

  useWebSocket<{ type: string; game?: Game }>(
    `/ws/games/${gameId}`,
    useCallback((msg) => {
      if (msg.game) setGame(msg.game)
    }, []),
  )

  if (!game) {
    return (
      <div className="panel rounded-xl p-4 text-sm text-[var(--color-ink-soft)]">Connecting to game…</div>
    )
  }

  return <WatchPanelBody game={game} onClose={onClose} />
}

function WatchPanelBody({ game, onClose }: { game: Game; onClose: () => void }) {
  const review = useGameReview(game.moves, game.fen)
  const evaluation = useReviewEvaluation(
    review.isLive,
    game.evaluation,
    review.displayFen,
    review.ply,
    game.eval_history,
    game.white.weights,
    game.black.weights,
  )

  return (
    <div className="panel animate-[fadeUp_400ms_ease] rounded-xl p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">
            {game.white.name} vs {game.black.name}
          </p>
          <p className="text-xs text-[var(--color-ink-soft)]">
            <StatusPill status={game.status} />{' '}
            {game.result ? `· ${game.result}` : `· move ${game.moves.length}`}
          </p>
        </div>
        <button type="button" onClick={onClose} className="btn-secondary rounded px-2 py-1 text-xs">
          Close
        </button>
      </div>
      <div className="flex items-stretch gap-2">
        <EvalBar evaluation={evaluation} height={280} orientation="white" />
        <Board fen={review.displayFen} boardWidth={280} />
      </div>
      <div className="mt-3">
        <MoveControls
          ply={review.ply}
          total={game.moves.length}
          isLive={review.isLive}
          canPrev={review.canPrev}
          canNext={review.canNext}
          onStart={review.goStart}
          onPrev={review.goPrev}
          onNext={review.goNext}
          onLive={review.goLive}
        />
      </div>
      <MoveList
        moves={game.moves}
        ply={review.ply}
        onSelectPly={review.goToPly}
        className="mt-3 max-h-28 overflow-auto"
      />
    </div>
  )
}
