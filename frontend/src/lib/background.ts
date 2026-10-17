// The slow 3D railway behind the app pages. This file only decides whether it should run; the
// scene itself lives in components/background and is loaded on demand.
const KEY = 'marg-sanyog-3d-background'

/** The visitor's choice: on unless they switched it off. */
export function backgroundWanted(): boolean {
  try {
    return localStorage.getItem(KEY) !== 'off'
  } catch {
    return true
  }
}

export function saveBackgroundWanted(on: boolean): void {
  try {
    localStorage.setItem(KEY, on ? 'on' : 'off')
  } catch {
    // storage can be blocked; the choice then lasts until the page is closed
  }
}

/** Never for people who asked for less motion, and not for automated browsers (the real-browser
 * smoke test and the unit tests have no use for it). */
export function backgroundSupported(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  if (typeof navigator !== 'undefined' && navigator.webdriver) return false
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
