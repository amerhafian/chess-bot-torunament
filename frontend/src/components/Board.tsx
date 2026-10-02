import { Chessboard } from 'react-chessboard'
import type { CSSProperties } from 'react'

type Props = {
  fen: string
  orientation?: 'white' | 'black'
  onPieceDrop?: (source: string, target: string) => boolean
  arePiecesDraggable?: boolean
  boardWidth?: number
  className?: string
}

export function Board({
  fen,
  orientation = 'white',
  onPieceDrop,
  arePiecesDraggable = false,
  boardWidth = 360,
  className = '',
}: Props) {
  const customBoardStyle: CSSProperties = {
    borderRadius: '4px',
    boxShadow: '0 12px 28px rgba(26, 20, 16, 0.28)',
    width: boardWidth,
  }

  return (
    <div className={`inline-block ${className}`} style={{ width: boardWidth }}>
      <Chessboard
        options={{
          position: fen,
          boardOrientation: orientation,
          allowDragging: arePiecesDraggable,
          boardStyle: customBoardStyle,
          darkSquareStyle: { backgroundColor: '#b58863' },
          lightSquareStyle: { backgroundColor: '#f0d9b5' },
          onPieceDrop: onPieceDrop
            ? ({ sourceSquare, targetSquare }) => {
                if (!targetSquare) return false
                return onPieceDrop(sourceSquare, targetSquare)
              }
            : undefined,
        }}
      />
    </div>
  )
}
