import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { canAnimate, stepForProgress } from '../../lib/home'
import { FEATURES, INTRO, RESULTS, STEPS } from './content'
import { HeroScene } from './scene/HeroScene'
import './home.css'

// How many pixels of scrolling it takes the train to reach the end of the line.
const SCROLL_DISTANCE = 3000

export function HomePage() {
  const { user } = useAuth()
  const rootRef = useRef<HTMLDivElement>(null)
  const heroRef = useRef<HTMLElement>(null)

  const [animated, setAnimated] = useState(canAnimate)
  const [reportedStep, setStep] = useState(-1)
  const step = animated ? reportedStep : -1

  // Follow the window size and the "reduce motion" setting.
  useEffect(() => {
    const update = () => setAnimated(canAnimate())
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  useEffect(() => {
    document.title = 'MARG SANYOG: plan every closure once'
    window.scrollTo(0, 0)
  }, [])

  // The scene reports how far the journey has gone; only a change of station re-renders this page.
  const onProgress = (progress: number) => setStep(stepForProgress(progress))

  const goTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  const current = step >= 0 ? STEPS[step] : null

  return (
    <div className="home" ref={rootRef}>
      <header className="home-nav">
        <div className="home-brand">
          <span className="home-mark" aria-hidden="true">
            //
          </span>
          MARG SANYOG
        </div>
        <nav className="home-links" aria-label="Page sections">
          <button type="button" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            Overview
          </button>
          <button type="button" onClick={() => goTo('features')}>
            Features
          </button>
          <button type="button" onClick={() => goTo('results')}>
            Results
          </button>
        </nav>
        {user ? (
          <Link className="home-cta home-cta-dark" to="/dashboard">
            Open dashboard
          </Link>
        ) : (
          <Link className="home-cta home-cta-dark" to="/login">
            Log in
          </Link>
        )}
      </header>

      <section className={`home-hero${animated ? ' home-hero-pinned' : ''}`} ref={heroRef} aria-label="Overview">
        <div className="hero-copy">
          <span className="hero-badge">
            <i aria-hidden="true" />
            Simulation: all data is synthetic
          </span>
          <h1>
            One closure
            <br />
            <span className="gradient-text">for every department.</span>
          </h1>
          <p className="hero-lead">
            Engineering, Traction and Signal and Telecom each ask for track time. MARG SANYOG plans their
            requests together, at the quietest hours, and shows a planner exactly why.
          </p>
          <div className="hero-actions">
            {user ? (
              <Link className="home-cta home-cta-primary" to="/dashboard">
                Open dashboard
              </Link>
            ) : (
              <Link className="home-cta home-cta-primary" to="/login">
                Log in
              </Link>
            )}
            <button type="button" className="home-cta home-cta-ghost" onClick={() => goTo('features')}>
              What it does
            </button>
          </div>

        </div>

        <HeroScene triggerRef={heroRef} animated={animated} scrollDistance={SCROLL_DISTANCE} onProgress={onProgress} />

        {animated && (
          <>
            <aside className="station-board" aria-live="polite" data-step={step}>
              <div className="board-head">
                <span>{current ? `Station ${step + 1} of ${STEPS.length}` : 'How it works'}</span>
                <span>{current ? current.who : 'Scroll to depart'}</span>
              </div>
              <div className="board-body" key={step}>
                <h2>{current ? current.title : INTRO.title}</h2>
                <p>{current ? current.text : INTRO.text}</p>
              </div>
              <ol className="board-stops" aria-label="Stops">
                {STEPS.map((s, i) => (
                  <li key={s.title} className={step >= i ? 'reached' : ''}>
                    {s.title}
                  </li>
                ))}
              </ol>
            </aside>
            <div className="scroll-hint">
              <span>Scroll to drive the train</span>
              <div className="mouse" aria-hidden="true">
                <div />
              </div>
            </div>
          </>
        )}
      </section>

      {!animated && (
        <section className="home-section" aria-label="How it works">
          <h2 className="section-title">How it works</h2>
          <ol className="steps-static">
            {STEPS.map((s, index) => (
              <li key={s.title}>
                <span className="steps-number">{index + 1}</span>
                <div>
                  <h3>{s.title}</h3>
                  <p className="muted">{s.who}</p>
                  <p>{s.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="home-section" id="features">
        <h2 className="section-title">What it does for a railway division</h2>
        <div className="feature-grid">
          {FEATURES.map((feature) => (
            <article className="feature" key={feature.title}>
              <h3>{feature.title}</h3>
              <p>{feature.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="home-section home-section-dark" id="results">
        <h2 className="section-title">An example run</h2>
        <p className="section-lead">
          16 requests across 4 sections for one week, planned independently and then together. These
          numbers come from <strong>simulated data</strong> and say nothing about real railways.
        </p>
        <div className="result-grid">
          {RESULTS.map((result) => (
            <div className="result" key={result.label}>
              <div className="result-label">{result.label}</div>
              <div className="result-values">
                <span className="result-before">{result.before}</span>
                <span aria-hidden="true">→</span>
                <span className="result-after">{result.after}</span>
              </div>
              <div className="result-change">
                {Math.round((1 - result.after / result.before) * 100)}% lower with joint planning
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="home-section home-final" id="start">
        <h2 className="section-title">Arrived at the terminal</h2>
        <p className="section-lead">
          Sign in to request blocks, run a plan and review the result. The planner proposes; people approve.
        </p>
        {user ? (
          <Link className="home-cta home-cta-primary" to="/dashboard">
            Open dashboard
          </Link>
        ) : (
          <Link className="home-cta home-cta-primary" to="/login">
            Log in
          </Link>
        )}
      </section>

    </div>
  )
}
