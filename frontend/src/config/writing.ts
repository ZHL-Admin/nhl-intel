/**
 * Writing manifest — the ordered list of published posts, newest first. Today's M7 module and (from
 * P4) the `/learn/writing` index both read this. Entries are added only when the owner supplies the
 * final markdown; placeholder copy is forbidden, so this ships EMPTY until the benchmark post lands.
 *
 * The benchmark piece's stable URL is `/learn/writing/beating-marcel` (D19), i.e. `slug: 'beating-marcel'`.
 * When it's ready, add its markdown under `frontend/content/writing/` and prepend an entry here.
 */
export interface WritingEntry {
  slug: string
  title: string
  /** ISO date (YYYY-MM-DD) of publication. */
  date: string
  /** One-line standfirst shown under the title. */
  dek: string
}

export const WRITING: WritingEntry[] = []
