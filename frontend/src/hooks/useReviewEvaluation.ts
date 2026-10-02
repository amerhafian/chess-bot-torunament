import { useEffect, useMemo, useRef, useState } from 'react'
import {
  api,
  weightsToEvaluatePayload,
  type Evaluation,
  type Weights,
} from '../api'

const BAR_SCALE = 3
const LIVE_EMA = 0.35
const MATE_THRESHOLD = 50000

function mateLabel(score: number): string | null {
  if (Math.abs(score) < MATE_THRESHOLD) return null
  const plies = Math.max(0, Math.round(100000 - Math.abs(score)))
  const moves = Math.max(1, Math.floor((plies + 1) / 2))
  return score > 0 ? `M${moves}` : `-M${moves}`
}

function isMateLabel(label: string | undefined): boolean {
  return Boolean(label && /^-?M\d+$/.test(label))
}

function scoreToBar(score: number): Evaluation {
  const mate = mateLabel(score)
  if (mate) {
    return {
      score,
      white_pct: score > 0 ? 100 : 0,
      label: mate,
      source: 'search',
    }
  }
  const white_pct = Math.max(0, Math.min(100, 50 + 50 * Math.tanh(score / BAR_SCALE)))
  const label = `${score >= 0 ? '+' : ''}${score.toFixed(1)}`
  return { score, white_pct, label, source: 'search' }
}

/**
 * Live: prefer server search evaluation, EMA-smoothed for the bar.
 * Review: use eval_history[ply-1] when present (exact, no EMA); otherwise static fallback.
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
  const [smoothedLive, setSmoothedLive] = useState<Evaluation | undefined>(liveEvaluation)
  const smoothPct = useRef<number | null>(null)

  useEffect(() => {
    if (!isLive || !liveEvaluation) {
      if (!isLive) smoothPct.current = null
      setSmoothedLive(liveEvaluation)
      return
    }
    const target = liveEvaluation.white_pct
    if (smoothPct.current === null || isMateLabel(liveEvaluation.label)) {
      smoothPct.current = target
    } else {
      smoothPct.current = smoothPct.current * (1 - LIVE_EMA) + target * LIVE_EMA
    }
    setSmoothedLive({
      ...liveEvaluation,
      white_pct: smoothPct.current,
    })
  }, [isLive, liveEvaluation])

  const w1 = weightsToEvaluatePayload(weights)
  const w2 = weights2 ? weightsToEvaluatePayload(weights2) : undefined

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
          ...w1,
          ...(w2 ? { weights2: w2 } : {}),
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
  }, [
    isLive,
    historyEval,
    fen,
    w1.a1,
    w1.a2,
    w1.b1,
    w1.b2,
    w1.c1,
    w1.c2,
    w1.d1,
    w1.d2,
    w1.e1,
    w1.e2,
    w2?.a1,
    w2?.a2,
    w2?.b1,
    w2?.b2,
    w2?.c1,
    w2?.c2,
    w2?.d1,
    w2?.d2,
    w2?.e1,
    w2?.e2,
  ])

  if (isLive) return smoothedLive ?? liveEvaluation
  return historyEval ?? fallback
}
