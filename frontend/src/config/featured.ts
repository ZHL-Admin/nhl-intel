/**
 * Home "Featured" content (doc 19 §9). Points at the draft-pick-value essay ("What a draft pick is
 * really worth", doc 16 §2) once it exists in the Writing manifest; until then it features the Draft
 * Value tool with a pick-lookup hook. Reading from config keeps swapping the target a DATA change,
 * not a layout change (per owner).
 */
import { WRITING } from './writing'

export interface FeaturedContent {
  eyebrow: string
  title: string
  dek: string
  to: string
  linkLabel: string
}

/** When the essay lands, add it to WRITING under this slug and Featured points to it automatically. */
const DRAFT_ESSAY_SLUG = 'what-a-draft-pick-is-really-worth'

export function resolveFeatured(): FeaturedContent {
  const essay = WRITING.find((w) => w.slug === DRAFT_ESSAY_SLUG)
  if (essay) {
    return { eyebrow: 'Featured', title: essay.title, dek: essay.dek, to: `/learn/writing/${essay.slug}`, linkLabel: 'Read' }
  }
  // Fallback until the essay is written: the Draft Value tool, framed as a pick-lookup hook.
  return {
    eyebrow: 'Featured',
    title: 'What is pick #6 actually worth?',
    dek: 'The empirical value of every draft slot, in WAR.',
    to: '/studio/draft',
    linkLabel: 'Open Draft Value',
  }
}
