import { useParams } from 'react-router-dom'
import Shell from '../shell/Shell'
import Placeholder from './Placeholder'

/** A single note (§3.2). MDX reading column + figures; built in Step 3. */
export default function Note() {
  const { slug } = useParams()
  return (
    <Shell>
      <div className="rt-reading">
        <Placeholder
          title="Note"
          kicker="Research Note"
          step="Step 3 (Notes)"
          note={`Slug: ${slug ?? '(none)'} — resolved from content/notes/*.mdx at build time.`}
        />
      </div>
    </Shell>
  )
}
