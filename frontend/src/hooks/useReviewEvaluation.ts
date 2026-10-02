import { useEffect, useState } from 'react'
import { api, type Evaluation, type Weights } from '../api'

/** Live eval from server payload, or fetch eval for a reviewed FEN. */
export function useReviewEvaluation(
  isLive: boolean,
  liveEvaluation: Evaluation | undefined,
  fen: string,
  weights: Weights,
  weights2?: Weights,
) {
  const [evaluation, setEvaluation] = useState<Evaluation | undefined>(liveEvaluation)

  useEffect(() => {
    if (isLive) {
      setEvaluation(liveEvaluation)
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
          ...(weights2
            ? { a2: weights2.a, b2: weights2.b, c2: weights2.c }
            : {}),
        })
        .then((ev) => {
          if (!cancelled) setEvaluation(ev)
        })
        .catch(() => undefined)
    }, 80)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [isLive, liveEvaluation, fen, weights.a, weights.b, weights.c, weights2?.a, weights2?.b, weights2?.c])

  return evaluation
}
