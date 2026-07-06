/**
 * Methods library curation (P4). Ordered, grouped list of methodology docs surfaced on /learn/methods.
 * `slug` is the filename (without .md) under docs/methodology/. Any .md present but NOT listed here is
 * still shown — it falls into a trailing "More" group using its filename as the title — so a new doc is
 * never invisible. Groups render in GROUP_ORDER; entries render in array order within their group.
 */
export interface MethodEntry {
  slug: string
  title: string
  group: string
  blurb: string
}

export const METHOD_GROUPS = ['Player value', 'Models', 'Process'] as const
export const MORE_GROUP = 'More'
export const GROUP_ORDER: string[] = [...METHOD_GROUPS, MORE_GROUP]

export const METHODS: MethodEntry[] = [
  { slug: 'player-assessment', title: 'Player assessment', group: 'Player value', blurb: 'The three-layer read: tier, confidence, and role.' },
  { slug: 'assessment-prereg', title: 'Preregistrations', group: 'Process', blurb: 'What we committed to measuring, before the season, on the record.' },
  { slug: 'value-gar', title: 'Value and GAR', group: 'Player value', blurb: 'Goals above replacement — how the one number is built.' },
  { slug: 'player-context', title: 'Context: usage, quality, WOWY', group: 'Player value', blurb: 'The situation a player faced — deployment, competition, and with/without teammates.' },
  { slug: 'roster-projection', title: 'Roster projection', group: 'Models', blurb: 'Turning a roster into a projected points total, with a band.' },
  { slug: 'win-probability', title: 'Win probability', group: 'Models', blurb: 'Live win odds from the game state and the chances on the board.' },
  { slug: 'archetypes', title: 'Archetypes', group: 'Models', blurb: 'How players are clustered into playing styles.' },
  { slug: 'player-radar', title: 'Radar and labels', group: 'Player value', blurb: 'The radar axes and the labels that summarize them.' },
  { slug: 'player-verdict', title: 'Verdicts', group: 'Player value', blurb: 'How the one-line verdict on a player is assembled.' },
]

/** The methodology doc a data surface links to (replaces the P2 LEARN_LINKS_PENDING marker). */
export const METHOD_LINKS = {
  power: '/learn/methods/power-ratings',
  deserved: '/learn/methods/reconciliation',
} as const
