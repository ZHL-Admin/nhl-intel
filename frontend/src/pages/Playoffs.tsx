import { useState, useEffect, useMemo } from 'react'
import { usePageTitle } from '../hooks/usePageTitle'
import { RotateCcw } from 'lucide-react'
import { PageLayout, PageCard, SkeletonLoader } from '../components/common'
import { getPlayoffBracket } from '../api/playoffs'
import { PlayoffBracket } from '../api/types'
import { getTeamLogoUrl, getTeamName, getTeamColor } from '../utils/teams'
import './Playoffs.css'

const pct = (v: number) => `${Math.round(v * 100)}%`
type Pair = [string, string]

/** One interactive series: click either team to advance them. Winner is highlighted in team color;
 * an underdog pick is tagged as an upset. */
function SeriesCard({ id, a, b, aProb, winner, favorite, onPick, size = 'md' }: {
  id: string; a: string; b: string; aProb: number; winner: string; favorite: string
  onPick: (id: string, team: string) => void; size?: 'md' | 'lg'
}) {
  const row = (team: string) => {
    const p = team === a ? aProb : 1 - aProb
    const isWinner = winner === team
    const isUpset = isWinner && team !== favorite
    return (
      <button
        type="button"
        className={`pl-series__team${isWinner ? ' is-winner' : ''}`}
        style={isWinner ? ({ ['--pl-team' as any]: getTeamColor(team) }) : undefined}
        onClick={() => onPick(id, team)}
        aria-pressed={isWinner}
      >
        <img className="pl-series__logo" src={getTeamLogoUrl(team)} alt="" loading="lazy" />
        <span className="pl-series__name">
          <span className="pl-series__abbr">{team}</span>
          {isUpset && <span className="pl-series__upset" title="Upset pick — the underdog">▲</span>}
        </span>
        <span className="pl-series__prob mono">{pct(p)}</span>
      </button>
    )
  }
  return (
    <div className={`pl-series pl-series--${size}`}>
      {row(a)}
      {row(b)}
    </div>
  )
}

/** scale grows toward the center so cards get bigger round by round (the Final is the largest). */
function Column({ label, scale = 1, children }: { label: string; scale?: number; children: React.ReactNode }) {
  return (
    <div className="pl-col" style={{ ['--s' as any]: scale }}>
      <div className="pl-col__label">{label}</div>
      <div className="pl-col__body">{children}</div>
    </div>
  )
}

export default function Playoffs() {
  usePageTitle('Playoffs')
  const [bracket, setBracket] = useState<PlayoffBracket | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [picks, setPicks] = useState<Record<string, string>>({})

  useEffect(() => {
    let active = true
    getPlayoffBracket()
      .then((b) => active && setBracket(b))
      .catch(() => active && setError('Failed to load the playoff prediction.'))
    return () => { active = false }
  }, [])

  // P(a wins) and the higher seed for any pairing, from the precomputed model matrix.
  const pw = useMemo(() => {
    const prob = new Map<string, number>()
    const seed = new Map<string, string>()
    bracket?.pairwise.forEach((p) => {
      prob.set(`${p.a}|${p.b}`, p.a_winprob)
      prob.set(`${p.b}|${p.a}`, 1 - p.a_winprob)
      seed.set(`${p.a}|${p.b}`, p.higher_seed)
      seed.set(`${p.b}|${p.a}`, p.higher_seed)
    })
    return { prob, seed }
  }, [bracket])

  const PLAYOFFS_SUB = 'Build your own bracket — click any team to advance them — against the model’s Monte-Carlo odds.'

  if (error) {
    return (
      <PageLayout>
        <PageCard title="Playoffs" subtitle={PLAYOFFS_SUB}>
          <p className="pl-error">{error}</p>
        </PageCard>
      </PageLayout>
    )
  }
  if (!bracket) {
    return (
      <PageLayout>
        <PageCard title="Playoffs" subtitle={PLAYOFFS_SUB}>
          <SkeletonLoader height={80} />
          <div style={{ marginTop: 24 }}><SkeletonLoader height={420} /></div>
        </PageCard>
      </PageLayout>
    )
  }

  const prob = (a: string, b: string) => pw.prob.get(`${a}|${b}`) ?? 0.5
  // Within this window of a coin flip, the default advances the higher seed (home-ice tiebreak)
  // rather than a razor-thin rating edge — matching the model's bracket.
  const TIE_EPS = 0.02
  const favorite = (a: string, b: string) => {
    const p = prob(a, b)
    if (Math.abs(p - 0.5) < TIE_EPS) return pw.seed.get(`${a}|${b}`) ?? (p >= 0.5 ? a : b)
    return p >= 0.5 ? a : b
  }
  // winner = the user's pick if it's still one of the two teams, else the model favorite.
  const winnerOf = (id: string, a: string, b: string) =>
    (picks[id] === a || picks[id] === b) ? picks[id] : favorite(a, b)

  // Build the bracket bottom-up. Round 1 is fixed; later rounds are formed by the winners below.
  const r1: Pair[] = bracket.rounds[0].map((s) => [s.high.abbrev, s.low.abbrev])
  const w1 = r1.map((p, i) => winnerOf(`r1-${i}`, p[0], p[1]))
  const r2: Pair[] = [[w1[0], w1[1]], [w1[2], w1[3]], [w1[4], w1[5]], [w1[6], w1[7]]]
  const w2 = r2.map((p, i) => winnerOf(`r2-${i}`, p[0], p[1]))
  const cf: Pair[] = [[w2[0], w2[1]], [w2[2], w2[3]]]
  const wcf = cf.map((p, i) => winnerOf(`cf-${i}`, p[0], p[1]))
  const fin: Pair = [wcf[0], wcf[1]]
  const champ = winnerOf('final', fin[0], fin[1])

  // Picking a winner invalidates the matchups above it, so clear those ancestor picks.
  const ancestorsOf = (id: string): string[] => {
    const [r, nStr] = id.split('-'); const n = parseInt(nStr)
    if (r === 'r1') return [`r2-${n >> 1}`, `cf-${n >> 2}`, 'final']
    if (r === 'r2') return [`cf-${n >> 1}`, 'final']
    if (r === 'cf') return ['final']
    return []
  }
  const pick = (id: string, team: string) => setPicks((prev) => {
    const next = { ...prev, [id]: team }
    ancestorsOf(id).forEach((a) => delete next[a])
    return next
  })

  // Any series whose winner isn't the model favorite = the user has built an upset path.
  const allSeries: { id: string; pair: Pair }[] = [
    ...r1.map((p, i) => ({ id: `r1-${i}`, pair: p })),
    ...r2.map((p, i) => ({ id: `r2-${i}`, pair: p })),
    ...cf.map((p, i) => ({ id: `cf-${i}`, pair: p })),
    { id: 'final', pair: fin },
  ]
  const modified = allSeries.some(({ id, pair }) =>
    winnerOf(id, pair[0], pair[1]) !== favorite(pair[0], pair[1]))

  // The champion's run: the four opponents it had to beat, and the joint probability of that path.
  const pairWith = (pairs: Pair[]) => pairs.find((p) => p.includes(champ))
  const pathPairs = [pairWith(r1), pairWith(r2), pairWith(cf), fin].filter(Boolean) as Pair[]
  const pathProb = pathPairs.reduce((acc, p) => {
    const opp = p[0] === champ ? p[1] : p[0]
    return acc * prob(champ, opp)
  }, 1)
  const champModelOdds = bracket.odds.find((o) => o.abbrev === champ)?.win_cup

  const card = (id: string, pair: Pair, size: 'md' | 'lg' = 'md') => (
    <SeriesCard
      id={id} a={pair[0]} b={pair[1]} aProb={prob(pair[0], pair[1])}
      winner={winnerOf(id, pair[0], pair[1])} favorite={favorite(pair[0], pair[1])}
      onPick={pick} size={size}
    />
  )

  return (
    <PageLayout>
      <PageCard title="Playoffs" subtitle={PLAYOFFS_SUB}>
        <div className="pl-hero" style={{ ['--pl-team' as any]: getTeamColor(champ) }}>
          <div className="pl-champion">
            <div className="pl-champion__head">
              <span className="pl-champion__label">
                {modified ? 'Your Bracket Champion' : 'Predicted Champion'}
              </span>
              {modified && (
                <button className="pl-reset" onClick={() => setPicks({})}>
                  <RotateCcw size={13} /> Reset to model
                </button>
              )}
            </div>
            <div className="pl-champion__team">
              <img className="pl-champion__logo" src={getTeamLogoUrl(champ)} alt="" />
              <div>
                <div className="pl-champion__name">{getTeamName(champ)}</div>
                <div className="pl-champion__odds mono">
                  {pct(pathProb)} chance of this run
                  {champModelOdds != null && ` · ${pct(champModelOdds)} model cup odds`}
                </div>
              </div>
            </div>
            <p className="pl-champion__hint">Click any team to advance them and build your own path.</p>
          </div>

          {/* Mirrored bracket: West flows to the center, East flows in from the right. */}
          <section className="pl-bracket-wrap">
            <div className="pl-bracket">
              <Column label="First Round" scale={0.85}>
                {[0, 1, 2, 3].map((i) => <span key={`wr1-${i}`}>{card(`r1-${i}`, r1[i])}</span>)}
              </Column>
              <Column label="Second Round" scale={0.95}>
                {[0, 1].map((i) => <span key={`wr2-${i}`}>{card(`r2-${i}`, r2[i])}</span>)}
              </Column>
              <Column label="Conf. Final" scale={1.06}>{card('cf-0', cf[0])}</Column>
              <Column label="Final" scale={1.2}>{card('final', fin, 'lg')}</Column>
              <Column label="Conf. Final" scale={1.06}>{card('cf-1', cf[1])}</Column>
              <Column label="Second Round" scale={0.95}>
                {[2, 3].map((i) => <span key={`er2-${i}`}>{card(`r2-${i}`, r2[i])}</span>)}
              </Column>
              <Column label="First Round" scale={0.85}>
                {[4, 5, 6, 7].map((i) => <span key={`er1-${i}`}>{card(`r1-${i}`, r1[i])}</span>)}
              </Column>
            </div>
            <div className="pl-bracket__conf">
              <span>Western Conference</span><span>Eastern Conference</span>
            </div>
          </section>
        </div>

        <div className="page-divider" />

        {/* Championship odds from the Monte-Carlo simulation (the model's own, independent of picks) */}
        <section className="pl-odds-section">
          <h2 className="pl-odds-section__title">Championship odds</h2>
          <p className="pl-odds-section__sub">
            {bracket.odds.length} teams, from 20,000 simulated brackets.
          </p>
          <table className="pl-odds">
            <thead>
              <tr>
                <th className="pl-odds__th-team">Team</th>
                <th>2nd Rd</th><th>Conf. Final</th><th>Final</th><th>Win Cup</th>
              </tr>
            </thead>
            <tbody>
              {bracket.odds.map((o) => (
                <tr key={o.abbrev}>
                  <td className="pl-odds__team">
                    <img src={getTeamLogoUrl(o.abbrev)} alt="" className="pl-odds__logo" loading="lazy" />
                    <span className="pl-odds__name">{getTeamName(o.abbrev)}</span>
                  </td>
                  <td className="mono">{pct(o.reach_round2)}</td>
                  <td className="mono">{pct(o.reach_conf_final)}</td>
                  <td className="mono">{pct(o.reach_final)}</td>
                  <td className="pl-odds__cup">
                    <span className="pl-odds__bar" style={{ width: `${o.win_cup * 100}%`, background: getTeamColor(o.abbrev) }} />
                    <span className="mono pl-odds__cupval">{(o.win_cup * 100).toFixed(1)}%</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </PageCard>
    </PageLayout>
  )
}
