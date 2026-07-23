import Shell from '../shell/Shell'
import Placeholder from './Placeholder'

/** Notes index (§3.3). Reverse-chron list of published notes; built in Step 3. */
export default function NotesIndex() {
  return (
    <Shell>
      <Placeholder
        title="Notes"
        step="Step 3 (Notes)"
        note="The MDX pipeline generates this list from note frontmatter."
      />
    </Shell>
  )
}
