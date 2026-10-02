import { Chess } from 'chess.js'
import { useCallback, useEffect, useMemo, useState } from 'react'

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

/** Replay SAN moves and return FEN after `ply` half-moves (0 = start). */
export function fenAfterPly(moves: string[], ply: number): string {
  const chess = new Chess()
  const limit = Math.max(0, Math.min(ply, moves.length))
  for (let i = 0; i < limit; i++) {
    const result = chess.move(moves[i])
    if (!result) break
  }
  return chess.fen()
}

export function useGameReview(moves: string[], liveFen: string) {
  const [ply, setPly] = useState(moves.length)
  const [followingLive, setFollowingLive] = useState(true)

  useEffect(() => {
    setPly((prev) => {
      if (followingLive) return moves.length
      return Math.min(prev, moves.length)
    })
  }, [moves.length, followingLive])

  const isLive = followingLive || ply >= moves.length

  const displayFen = useMemo(() => {
    if (isLive) return liveFen || fenAfterPly(moves, moves.length)
    return fenAfterPly(moves, ply)
  }, [isLive, liveFen, moves, ply])

  const goStart = useCallback(() => {
    setFollowingLive(false)
    setPly(0)
  }, [])

  const goPrev = useCallback(() => {
    setFollowingLive(false)
    setPly((p) => {
      const current = followingLive ? moves.length : p
      return Math.max(0, current - 1)
    })
  }, [followingLive, moves.length])

  const goNext = useCallback(() => {
    setPly((p) => {
      const current = followingLive ? moves.length : p
      const next = Math.min(moves.length, current + 1)
      setFollowingLive(next >= moves.length)
      return next
    })
  }, [followingLive, moves.length])

  const goLive = useCallback(() => {
    setFollowingLive(true)
    setPly(moves.length)
  }, [moves.length])

  const goToPly = useCallback(
    (target: number) => {
      const next = Math.max(0, Math.min(moves.length, target))
      if (next >= moves.length) {
        setFollowingLive(true)
        setPly(moves.length)
      } else {
        setFollowingLive(false)
        setPly(next)
      }
    },
    [moves.length],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        goPrev()
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        goNext()
      } else if (e.key === 'Home') {
        e.preventDefault()
        goStart()
      } else if (e.key === 'End') {
        e.preventDefault()
        goLive()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [goPrev, goNext, goStart, goLive])

  return {
    ply: isLive ? moves.length : ply,
    displayFen: displayFen || START_FEN,
    isLive,
    goStart,
    goPrev,
    goNext,
    goLive,
    goToPly,
    canPrev: (isLive ? moves.length : ply) > 0,
    canNext: !isLive,
  }
}
