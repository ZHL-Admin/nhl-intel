// The faceoff dot — geometrically identical to the interval-dot the site uses to plot every value
// estimate (the mark and the data language are the same shape). Inherits text color; never coloured.
export default function BrandMark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="12" cy="12" r="3.5" fill="currentColor" />
    </svg>
  )
}
