/**
 * DocMarkdown (P4) — renders a methodology/writing markdown string with GitHub-flavored tables.
 * Cross-doc links written as `foo.md` are rewritten to `/learn/methods/foo` so the library is
 * internally navigable; other links open in-tab (no new window). Code uses the existing mono token.
 */
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router-dom'
import './DocMarkdown.css'

export default function DocMarkdown({ content }: { content: string }) {
  return (
    <div className="doc-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href && href.endsWith('.md')) {
              const slug = href.replace(/^.*\//, '').replace(/\.md$/, '')
              return <Link to={`/learn/methods/${slug}`}>{children}</Link>
            }
            return <a href={href}>{children}</a>
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
