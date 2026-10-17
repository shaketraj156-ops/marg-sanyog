// The journey on the homepage, as fractions of the pinned scroll (0 at the top, 1 when the train
// has left the last station). The train brakes into each station at ARRIVE, stands at the
// platform, and pulls away at DEPART.
export const ARRIVE = [0.1, 0.32, 0.54, 0.76]
export const DEPART = [0.17, 0.39, 0.61, 0.88]

// Show a station's information a little before the train arrives, so it is there as it pulls in.
const LEAD = 0.03

/** Which station's information to show at a point of the journey: -1 is the introduction,
 * 0 to 3 a station. It stays on a station until the next one is about to arrive. */
export function stepForProgress(progress: number): number {
  let step = -1
  ARRIVE.forEach((arrive, index) => {
    if (progress >= arrive - LEAD) step = index
  })
  return step
}

/** True when the scroll-driven journey should run: not on narrow screens, where the pinned scene
 * does not fit. Those get the still picture. The "reduce motion" setting is not checked: the train
 * only moves while the visitor scrolls, and many laptops report that setting without the user
 * having chosen it (animations off in Windows, battery saver), which left the train standing. */
export function canAnimate(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(min-width: 800px)').matches
}
