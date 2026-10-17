import { useEffect, useRef } from 'react'
import type { BackgroundHandle } from './railwayScene'

/** A fixed full-screen canvas behind the pages. It reports when it is drawing (`onReady`) and when
 * it could not start (`onFail`, for example without WebGL), so the page can fall back to its plain look. */
export default function BackgroundScene({ onReady, onFail }: { onReady: () => void; onFail: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const callbacks = useRef({ onReady, onFail })
  useEffect(() => {
    callbacks.current = { onReady, onFail }
  })

  useEffect(() => {
    let cancelled = false
    let handle: BackgroundHandle | null = null
    const canvas = canvasRef.current
    if (!canvas) return
    import('./railwayScene')
      .then(({ createBackgroundScene }) => {
        if (cancelled) return
        try {
          handle = createBackgroundScene(canvas)
          callbacks.current.onReady()
        } catch (error) {
          console.warn('The 3D background could not start:', error)
          callbacks.current.onFail()
        }
      })
      .catch((error) => {
        console.warn('The 3D background could not be loaded:', error)
        callbacks.current.onFail()
      })
    return () => {
      cancelled = true
      handle?.dispose()
    }
  }, [])

  return <canvas ref={canvasRef} className="bg-canvas" aria-hidden="true" data-testid="background-3d" />
}
