// The words on the homepage. Numbers come from the project's own demo run on synthetic data
// (16 requests, 4 sections, 7 days) and are labelled as simulated wherever they appear.

export interface Step {
  title: string
  who: string
  text: string
}

export const INTRO = {
  title: 'Follow one block, start to finish',
  text: 'Scroll to drive the train through four stations: from a department asking for a block to a closure on the published calendar.',
}

export const STEPS: Step[] = [
  {
    title: 'Request',
    who: 'Engineering, Traction, Signal and Telecom',
    text: 'Each department asks for the blocks it needs: section, kind of work, duration, date window and priority. Rules such as "signal testing only after track work" are saved as dependencies.',
  },
  {
    title: 'Plan',
    who: 'The optimizer',
    text: 'A constraint solver picks a day and start time for every request. Work on the same section shares one closure window, scheduled when few trains run. An independent checker verifies every plan before it is saved.',
  },
  {
    title: 'Review',
    who: 'The planner',
    text: 'Every decision comes with a reason and the numbers behind it. Compare with independent planning, try a what-if move, or override the plan. Nothing is published without a person.',
  },
  {
    title: 'Publish',
    who: 'Planner or administrator',
    text: 'Approved closures go on the published calendar. Two blocks that overlap on the same section are refused, and every change is recorded in an audit log.',
  },
]

export const FEATURES = [
  {
    title: 'Fewer closures',
    text: 'Requests from different departments for the same section and days are merged into one closure instead of one each.',
  },
  {
    title: 'Quiet hours first',
    text: 'The planner knows how many trains run in every 30-minute slot and prefers the windows that disturb the fewest.',
  },
  {
    title: 'Decisions you can explain',
    text: 'Reason codes such as MERGED, LOW_TRAFFIC and DEPENDENCY_ORDER, each with the numbers it was computed from.',
  },
  {
    title: 'Always a valid plan',
    text: 'Crew limits, block length and dependencies are checked by a separate verifier. If the optimizer runs out of time, a valid starting plan is used.',
  },
  {
    title: 'People stay in charge',
    text: 'Try a move without saving it, override part of a plan, then approve and publish. Roles decide who can do what.',
  },
  {
    title: 'Learns, but safely',
    text: 'A delay model can replace plain train counts as the cost, only when it beats its baseline. Otherwise the planner falls back automatically.',
  },
]

export const RESULTS = [
  { label: 'Closures', before: 15, after: 10 },
  { label: 'Block hours', before: 35, after: 24 },
  { label: 'Trains affected', before: 56, after: 17 },
]
