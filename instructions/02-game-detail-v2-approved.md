# 02 · Game Detail v2 · APPROVED

Supersedes 02-game-detail.md. Comp: mockup-game-detail.html (final state,
VGK 2-4 CAR; also the first comp rendered on the v3 paper palette; use the
semantic.css migration map for any hex literals). Live and preview states
are specified here and fall under the standing first-build screenshot
review.

## 0. Amendment: the pole grammar (ratified)
A game page has two poles, not a subject. On any game surface, HOME takes
`--line-blue` and AWAY takes `--line-red` for ALL two-team data ink: worm
washes, pressure streams, head-to-head bars, goal dots, hinge swings,
shot-density heat, GSAx values. Team colors remain identity chrome only
(logo circles). The rule is declared once per page in a plain-words legend
at the top of the run of play ("{Home} reads blue · {Away} reads red,
everywhere on this page") and never re-explained. This generalizes the
matchup-tile grammar (17 v2) to neutral subjects; the Trade History
perspective rule (subject anchored, blue toward subject) is unchanged.
Valence coloring (good/bad) does not apply to pole-colored marks; the two
uses never co-occur on one element.

## 1. Header (the game scoreboard)
Back link "← Games · {date}". Row: away block (logo 40, city, "away"
micro), serif score 36, home block mirrored, FINAL status chip (mono).
Right block, exactly three elements: eyebrow "THE DESERVED SCORE · all
situations" (tooltip: xG definition, replacing the old footnote 1), serif
"{xG} – {xG} {leader city}", one context line (generated; e.g. "the team
that lost out-chanced the team that won"). Meta line below: round, game
number, date, venue, and the series state in ink weight 500 ("Carolina
wins the series 4-1" / "CAR leads 2-1"). Tabs right: The game · Box score
(box score lens keeps the existing table under system styling; spec
unchanged from v1 except tokens).

## 2. The verdict (one Panel, the page's only elevated object)
Eyebrow "THE VERDICT · FINAL" + "How we read a game" tooltip (xG, worm,
GSAx, game score definitions; kills the margin-note rail entirely: the
rail and superscript footnotes are retired on this page). Serif 22
verdict sentence (generated, template fallback from the deserved-score
gap and GSAx leader). Below a hairline: four receipt lines in two
columns, pole-dotted for team claims, gray for neutral observations; at
least one receipt must credit the losing side of the deserved score when
the deserved and actual winners differ.

## 3. The run of play (three lanes, shared x)
Period gridlines with mono P1/P2/P3. Lane one: win probability for the
home side, solid ink step line, 50% dashed reference, goals as pole-
colored dots with mono running-score labels, terminal value labeled. Lane
two: the chance worm (cumulative xG differential), solid ink line, even
reference, washes at 8-12%: above the line = away out-chancing in away's
pole color, below = home in home's (the caption states the reading in
words). Lane three: shot pressure per 60, two pole-colored streams at
14%. Hover scrubs all three lanes at once; goals open shot detail.
Everything observed is solid; nothing here is projected.

## 4. The hinges + the crease (two-column section)
Left, THE HINGES: the three largest win-probability swings, rows [mono
time | scorer bold + generated one-line description | signed WP swing in
the scorer's pole color], sorted by swing size. Right, THE CREASE: the
goalie duel table [goalie + team | saves/attempts by High/Med/Low danger
| GSAx signed and pole-colored | SV%]. SV% is computed saves over shots
(the old "NHL EDGE" column label is a bug; fixed). One-line caption
relating the GSAx swing to the final margin.

## 5. Head to head
Eyebrow + Raw/Adjusted text-tab lens (Adjusted = score-and-venue adjusted
5v5; tooltip on the tab). Two-column grid of stat strips, anatomy: [away
value | strip | home value]; eyebrow label centered above each strip;
center tick; bar leans toward the leader in the leader's pole color;
leader's value 600 ink, trailing value secondary. Rows: expected goals,
shots, 5v5 shot share, HD chances/60, power-play goals, faceoff wins,
hits, giveaways, takeaways. Inverted rows (giveaways: fewer leads) state
the reading in the section caption.

## 6. Where the chances came from
Full-width rink (radius-rink frame; the sanctioned rink use), shot-
attempt density folded to attacking ends as pole-colored heat fields,
goals as white-ringed pole dots, mono attempt-count labels per end. One
generated caption line. Tap opens the full shot chart (existing).

## 7. Who drove it
Top four skaters by game score: [name + "team · pos" | game score
(default sort, emphasis) | ixG | HDC | TOI], tooltip on game score,
"All skaters →" exit to the box score lens.

## 8. The work (collapsible, default expanded)
Left: period-by-period CF%/xGF% table with a generated reading line.
Right: the shot-quality ladder (attempts/goals by danger band per team)
with its reading line. Terms link to Methods; no footnotes anywhere.

## 9. Live state
Same skeleton, reordered honesty: status chip goes red LIVE with the
clock; the deserved-score block becomes WIN PROBABILITY (serif percent,
home side) with the deserved score demoted to its context line; the
verdict Panel is "THE STORY SO FAR" and regenerates on goals and period
breaks; timeline lanes draw left-to-right with a red now-marker at the
play head (the one sanctioned red rule remnant); hinges show the largest
swings so far; the crease and head-to-head update live; the rink map and
The Work render with partial data unapologetically. Poll cadence follows
the existing live feed.

## 10. Preview state
Header: no score; puck-drop time where the score sits; right block =
THE MATCHUP PRICED: serif win probability for the home side with the
model's line. Body: the verdict Panel becomes the preview verdict; then
projected goalies (two-row crease table with season GSAx), rolling form
(the last-10 5v5 CF% module lives HERE, not post-game; it was an empty
husk on the final page and is deleted from that state), season head-to-
head strips, and the season versions of the drivers. Sections that
require the game to exist (run of play, hinges, chance map) do not render
placeholder shells; they simply are not present.

## 11. Share and URL
Copy link per state; share card = header + verdict Panel (final), header
+ win probability + story so far (live), header + matchup priced
(preview). The game URL is permanent across states.

## 12. Data
All existing: shot-level xG, WP series, worm, pressure, game score, GSAx
by band, period splits, quality ladder, density maps, adjusted 5v5. New:
generated verdict/receipts/hinge descriptions/captions with template
fallbacks; the deserved-score context line; series-state string. No new
model output required.

## 13. Mobile
Header stacks (score row, then deserved score); timeline lanes go
full-width stacked with a shared scrubber; hinges above the crease;
head-to-head single column; rink map scrolls horizontally at min-width
560; The Work tables stack.

## 14. Acceptance
- Pole grammar audit: no team-color data ink anywhere; every two-team
  mark on the page resolves to home-blue/away-red; the legend renders
  once; valence and pole coloring never co-occur on one element.
- The deserved score equals the xG totals in head-to-head row one; the
  GSAx values match the crease table; the hinge swings match the WP lane
  at those timestamps.
- SV% column is computed correctly (regression test on this game: .920
  and .833).
- No margin notes, no superscript footnotes; every term reachable via
  tooltip or Methods.
- State machine: preview → live → final on one URL; rolling form appears
  only in preview; no placeholder shells for game-dependent sections.
- Verdict regenerates on live events; template fallbacks render when
  generation is unavailable.
- Both themes AA on the v3 paper tokens; tsc and build green.
