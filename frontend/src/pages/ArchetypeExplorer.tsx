/**
 * Archetype explainer (Learn). Two views the user can switch between to compare in practice:
 *  - GALLERY: browse the discovered discrete types — each a card with its characteristic centroid
 *    radar, measured traits, member count, and real exemplars.
 *  - STYLE-MAP: explore where real players actually sit in the (PCA-projected) feature space.
 * Archetypes are DISCOVERED clusters, not designable points: neither view lets you invent one, and
 * gaps between clusters read as empty. F and D are separate feature spaces (toggle, never co-plot).
 * Deep-linkable: ?view=map and ?type=F0 (so archetype tags link straight to a type).
 */
import { useEffect, useMemo, useState } from 'react'
import { usePageTitle } from '../hooks/usePageTitle'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { PageLayout, PageCard, Tabs, SkeletonLoader, PlayerAvatar } from '../components/common'
import SkillRadar from '../components/visualizations/SkillRadar'
import { getArchetypes } from '../api/archetypes'
import { ArchetypeCard, ArchetypeTrait, RadarSpoke } from '../api/types'
import { SHORT_SPOKE_LABELS, RADAR_ARC_GROUPS } from '../config/metrics'
import './ArchetypeExplorer.css'

const POS_NOUN: Record<string, string> = { F: 'forwards', D: 'defensemen' }
const traitPhrase = (t: ArchetypeTrait) => `${t.dir === '-' ? 'Low' : 'High'} ${t.label.toLowerCase()}`

/** Exemplar avatars + names; each links to the player's detail page. */
function Exemplars({ card, limit }: { card: ArchetypeCard; limit: number }) {
  return (
    <div className="arch-ex">
      {card.exemplars.slice(0, limit).map((e) => (
        <Link key={e.player_id} to={`/players/${e.player_id}`} className="arch-ex__item" title={`${e.name} (${e.season})`}>
          <PlayerAvatar id={e.player_id} team={e.team_abbrev} name={e.name} size={30} />
          <span className="arch-ex__name">{e.name}</span>
        </Link>
      ))}
    </div>
  )
}

function GalleryCard({ card, onOpen }: { card: ArchetypeCard; onOpen: (key: string) => void }) {
  return (
    <div className="arch-card">
      <button className="arch-card__main" onClick={() => onOpen(card.key)} aria-label={`Open ${card.name}`}>
        <div className="arch-card__head">
          <span className="arch-card__name">{card.name}</span>
          <span className="arch-card__count">{card.member_count}</span>
        </div>
        <div className="arch-card__radar">
          <SkillRadar spokes={card.centroid_radar} size={250} compact
            shortLabels={SHORT_SPOKE_LABELS} arcGroups={RADAR_ARC_GROUPS} />
        </div>
        <p className="arch-card__desc">{card.descriptor}</p>
      </button>
      <Exemplars card={card} limit={3} />
    </div>
  )
}

/** The fully-labeled reference radar shown ONCE atop the gallery — the axis key for the cards below. */
function ReferenceKey({ template, pos }: { template: RadarSpoke[]; pos: 'F' | 'D' }) {
  const ref = template.map((s) => ({ ...s, percentile: 50, sd: null }))
  return (
    <div className="arch-key">
      <div className="arch-key__radar">
        <SkillRadar spokes={ref} size={300} baseline={`Percentile vs ${POS_NOUN[pos]}`} />
      </div>
      <div className="arch-key__copy">
        <div className="arch-key__title">How to read these</div>
        <p>
          Each card below plots the same {template.length} axes — a player type's characteristic
          shape, as percentiles within {POS_NOUN[pos]}. The card labels are abbreviated and grouped
          (offense / special teams &amp; defense / style); <strong>hover any point</strong> on a card
          for the full axis name and exact value. Colours are the honesty tags shown here
          (skill / usage / style).
        </p>
      </div>
    </div>
  )
}

function ArchetypeDetail({ card, onBack }: { card: ArchetypeCard; onBack: () => void }) {
  const universal = card.universal_traits.slice(0, 6)
  return (
    <div className="arch-detail">
      <button className="arch-detail__back" onClick={onBack}><ArrowLeft size={15} /> All archetypes</button>
      <div className="arch-detail__grid">
        <div className="arch-detail__left">
          <h2 className="arch-detail__name">{card.name}</h2>
          <div className="arch-detail__meta">
            {card.family && <span className="arch-detail__fam">{card.family}</span>}
            <span>{card.member_count} player-seasons (2021–26)</span>
          </div>
          <p className="arch-detail__desc">{card.descriptor}</p>
          {universal.length > 0 && (
            <div className="arch-detail__block">
              <div className="arch-detail__block-title">What the type always shows</div>
              <div className="arch-detail__traits">
                {universal.map((t) => (
                  <span key={t.label} className={`arch-trait arch-trait--${t.dir === '-' ? 'low' : 'high'}`}>
                    {traitPhrase(t)} <small>{Math.round((t.share ?? 0) * 100)}%</small>
                  </span>
                ))}
              </div>
              <p className="arch-detail__note">
                “Always” = a measured universal: ≥80% of members on one side of the position median.
                The name asserts only these; the description above adds the distinctive shape.
              </p>
            </div>
          )}
          <div className="arch-detail__block">
            <div className="arch-detail__block-title">Exemplars (by membership strength)</div>
            <Exemplars card={card} limit={card.exemplars.length} />
          </div>
        </div>
        <div className="arch-detail__radar">
          <SkillRadar spokes={card.centroid_radar} baseline={`Characteristic shape · percentile vs ${POS_NOUN[card.pos_group]}`} size={360} />
        </div>
      </div>
    </div>
  )
}

function Gallery({ cards, pos, onOpen }: { cards: ArchetypeCard[]; pos: 'F' | 'D'; onOpen: (k: string) => void }) {
  const shown = cards.filter((c) => c.pos_group === pos)
  return (
    <>
      {shown[0] && <ReferenceKey template={shown[0].centroid_radar} pos={pos} />}
      <div className="arch-gallery">
        {shown.map((c) => <GalleryCard key={c.key} card={c} onOpen={onOpen} />)}
      </div>
    </>
  )
}

export default function ArchetypeExplorer() {
  usePageTitle('Archetypes')
  const [cards, setCards] = useState<ArchetypeCard[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()
  const pos = params.get('pos') === 'D' ? 'D' : 'F'
  const type = params.get('type')

  useEffect(() => {
    let active = true
    getArchetypes().then((c) => active && setCards(c)).catch(() => active && setError('Could not load archetypes.'))
    return () => { active = false }
  }, [])

  const setParam = (k: string, v: string | null) => {
    const next = new URLSearchParams(params)
    if (v == null) next.delete(k); else next.set(k, v)
    setParams(next, { replace: false })
  }

  // accept ?type= by cluster key (F0) OR by archetype name, so tags can deep-link without keys
  const selected = useMemo(
    () => cards?.find((c) => c.key === type || c.name === type) ?? null, [cards, type])
  // when a type is deep-linked, align the position toggle to it
  const effPos = selected ? (selected.pos_group as 'F' | 'D') : pos

  return (
    <PageLayout>
      <div className="arch">
        <PageCard
          title="Archetypes"
          subtitle="Archeypes are discovered by clustering. Browse the gallery to see each one's characteristic radar shape, what it always shows, and who exemplifies it."
          controls={!selected ? (
            <div className="arch__toolbar">
              <Tabs
                options={[{ value: 'F', label: 'Forwards' }, { value: 'D', label: 'Defense' }]}
                value={pos} onChange={(v) => setParam('pos', v)} />
            </div>
          ) : undefined}
        >
        {error && <p className="arch__msg">{error}</p>}
        {!cards && !error && <SkeletonLoader />}

        {cards && selected && <ArchetypeDetail card={selected} onBack={() => setParam('type', null)} />}

        {cards && !selected && (
          <Gallery cards={cards} pos={effPos} onOpen={(k) => setParam('type', k)} />
        )}
        </PageCard>
      </div>
    </PageLayout>
  )
}
