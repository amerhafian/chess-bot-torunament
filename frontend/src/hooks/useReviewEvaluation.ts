import { useEffect, useMemo, useState } from 'react'
import { api, type Evaluation, type Weights } from '../api'

function scoreToBar(score: number): Evaluation {
  const MATE = 50000
  if (score >= MATE) return { score, white_pct: 100, label: 'M', source: 'search' }
  if (score <= -MATE) return { score, white_pct: 0, label: '-M', source: 'search' }
  const white_pct = Math.max(0, Math.min(100, 50 + 50 * Math.tanh(score / 8)))
  const label = `${score >= 0 ? '+' : ''}${score.toFixed(1)}`
  return { score, white_pct, label, source: 'search' }
}

/**
 * Live: prefer server search evaluation.
 * Review: use eval_history[ply-1] when present; otherwise static /api/evaluate fallback.
 */
export function useReviewEvaluation(
  isLive: boolean,
  liveEvaluation: Evaluation | undefined,
  fen: string,
  ply: number,
  evalHistory: Array<number | null> | undefined,
  weights: Weights,
  weights2?: Weights,
) {
  const historyEval = useMemo(() => {
    if (isLive || ply <= 0 || !evalHistory || evalHistory.length === 0) return undefined
    const score = evalHistory[ply - 1]
    if (score === null || score === undefined) return undefined
    return scoreToBar(score)
  }, [isLive, ply, evalHistory])

  const [fallback, setFallback] = useState<Evaluation | undefined>(undefined)

  useEffect(() => {
    if (isLive) {
      setFallback(undefined)
      return
    }
    if (historyEval) {
      setFallback(undefined)
      return
    }
    let cancelled = false
    const t = window.setTimeout(() => {
      api
        .evaluate({
          fen,
          a: weights.a,
          b: weights.b,
          c: weights.c,
          ...(weights2 ? { a2: weights2.a, b2: weights2.b, c2: weights2.c } : {}),
        })
        .then((ev) => {
          if (!cancelled) setFallback(ev)
        })
        .catch(() => undefined)
    }, 80)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [isLive, historyEval, fen, weights.a, weights.b, weights.c, weights2?.a, weights2?.b, weights2?.c])

  if (isLive) return liveEvaluation
  return historyEval ?? fallback
}
