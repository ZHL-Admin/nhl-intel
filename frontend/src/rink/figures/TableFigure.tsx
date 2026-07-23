import type { ReactNode } from 'react'
import { Figure } from './Figure'

export interface Column<R> {
  key: string
  label: string
  /** custom cell render (e.g. sign coloring, dots) */
  render?: (row: R) => ReactNode
  /** className for the cell, e.g. 'pos' / 'neg' */
  className?: (row: R) => string | undefined
}

/**
 * Table figure — a styled data table inside a figure card with a mono caption.
 * Numbers are mono and right-aligned (first column left).
 */
export default function TableFigure<R extends Record<string, unknown>>({
  columns, rows, caption, n,
}: {
  columns: Column<R>[]
  rows: R[]
  caption?: ReactNode
  n?: number
}) {
  return (
    <Figure n={n} caption={caption} plain>
      <table className="rt-figtable">
        <thead>
          <tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key} className={c.className?.(row)}>
                  {c.render ? c.render(row) : String(row[c.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Figure>
  )
}
