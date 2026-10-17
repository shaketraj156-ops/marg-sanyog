import { useCallback, useEffect, useRef, useState } from 'react'
import { INTRO_SECONDS } from './introPath'
import type { IntroHandle } from './introScene'

const FADE_MS = 600

/** A short full-screen 3D welcome. It never blocks the app: if WebGL or the scene fails, it simply
 * closes, and the visitor can skip it with the button, Escape, Enter or Space. */
export default function IntroSplash({ name, onDone }: { name: string; onDone: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [leaving, setLeaving] = useState(false)
  const finished = useRef(false)
  const handle = useRef<IntroHandle | null>(null)
  const onDoneRef = useRef(onDone)
  useEffect(() => {
    onDoneRef.current = onDone
  })

  const finish = useCallback(() => {
    if (finished.current) return
    finished.current = true
    setLeaving(true)
    window.setTimeout(() => onDoneRef.current(), FADE_MS)
  }, [])

  useEffect(() => {
    let cancelled = false
    const canvas = canvasRef.current
    if (!canvas) return
    import('./introScene')
      .then(({ createIntroScene }) => {
        if (cancelled) return
        try {
          handle.current = createIntroScene(canvas, { onEnd: finish })
        } catch {
          onDoneRef.current() // no WebGL: carry on without the welcome
        }
      })
      .catch(() => onDoneRef.current())
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || event.key === 'Enter' || event.key === ' ') finish()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      cancelled = true
      window.removeEventListener('keydown', onKey)
      handle.current?.dispose()
      handle.current = null
    }
  }, [finish])

  const firstName = name.split(/\s+/)[0]
  return (
    <div className={`intro-overlay${leaving ? ' intro-leaving' : ''}`} role="dialog" aria-label="Welcome animation">
      <canvas ref={canvasRef} className="intro-canvas" aria-hidden="true" />
      <div className="intro-copy">
        <p className="intro-hello">Welcome, {firstName}</p>
        <p className="intro-title">MARG SANYOG</p>
        <p className="intro-tag">One closure for every department.</p>
      </div>
      <button type="button" className="intro-skip" onClick={finish} autoFocus>
        Skip
      </button>
      <div className="intro-progress" aria-hidden="true">
        <i style={{ animationDuration: `${INTRO_SECONDS}s` }} />
      </div>
    </div>
  )
}
