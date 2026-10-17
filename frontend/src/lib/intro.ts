// The short 3D welcome that plays once after signing in. This file only decides whether it should
// play; the scene itself lives in components/intro and is loaded on demand.
const KEY = 'marg-sanyog-intro'

/** Remember that the visitor has just signed in, so the next page shows the welcome. */
export function markIntroPending(): void {
  try {
    sessionStorage.setItem(KEY, '1')
  } catch {
    // storage can be blocked; the welcome is optional
  }
}

export function clearIntroFlag(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // nothing to do
  }
}

function pending(): boolean {
  try {
    return sessionStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

/** Play the welcome only right after a sign-in, and never for people who asked for less motion or
 * for automated browsers (the real-browser smoke test would be blocked by the overlay). */
export function shouldPlayIntro(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  if (typeof navigator !== 'undefined' && navigator.webdriver) return false
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false
  return pending()
}
