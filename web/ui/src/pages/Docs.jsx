import { useState, useMemo, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { useGuides, useGuide } from '../api'
import { PageTitle, PageSub, Spinner } from '../components/Shared'

// docs/ is a vault: pages live under concepts/, guides/, reference/ and
// architecture/, and the API addresses a subdirectory page as "dir--stem".
// The sidebar rebuilds that tree, in reading order — a visitor should meet
// the ideas before the look-up tables.
const SECTIONS = [
  { key: 'concepts',     label: 'Concepts',     blurb: 'The ideas. Read once.' },
  { key: 'guides',       label: 'Guides',       blurb: 'Task-shaped walkthroughs.' },
  { key: 'reference',    label: 'Reference',    blurb: 'Look things up.' },
  { key: 'architecture', label: 'Architecture', blurb: 'For changing the framework.' },
  { key: 'agents',       label: 'Agent SOPs',   blurb: 'Standard operating procedures.' },
]

// Internal working documents that ship in a source checkout but are not
// product documentation. The positioning doc is gitignored outright; the
// roadmap is a control document, not a guide.
const HIDDEN = new Set(['north-star', 'ROADMAP'])

// A distinctive fragment prefix, so a genuine in-page #anchor in the markdown
// is never mistaken for a cross-reference.
const WIKI_PREFIX = 'tb-doc:'

// Within a section, lead with the page that orients you.
const FIRST = { concepts: 'the-three-phase-workflow', guides: 'quickstart' }

const clean = t => (t || '').replace(/`/g, '')

function split(name) {
  const i = name.indexOf('--')
  return i === -1 ? { section: '', stem: name } : {
    section: name.slice(0, i), stem: name.slice(i + 2),
  }
}

/** Resolve a [[wiki link]] target to an API guide name, if one exists. */
function resolveWiki(target, byStem) {
  const stem = target.split('|')[0].split('#')[0].trim()
  return stem ? byStem.get(stem) : null
}

function Reader({ name, byStem, titles, onNavigate }) {
  const { data, isLoading, error } = useGuide(name)

  useEffect(() => { window.scrollTo({ top: 0, behavior: 'smooth' }) }, [name])

  if (isLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 24, color: 'var(--muted)', fontSize: 13 }}>
      <Spinner size={14} /> Loading…
    </div>
  )
  if (error) return <div style={{ padding: 16, color: 'var(--red-text)', fontSize: 13 }}>{error.message}</div>
  if (!data) return null

  // Wiki links are the vault's connective tissue; rendered as literal
  // "[[text]]" they are worse than no link at all. Rewrite each one to a
  // markdown link with a sentinel scheme the link renderer below turns into
  // an in-app navigation, so the graph works here the way it does in Obsidian.
  // The href is a fragment, not a custom scheme: react-markdown sanitizes
  // unknown protocols away (a "wiki:" href silently became no href at all,
  // which rendered every cross-reference as inert bold text).
  const content = data.content.replace(/\[\[([^\]]+)\]\]/g, (whole, inner) => {
    const [target, alias] = inner.split('|')
    const to = resolveWiki(target, byStem)
    // Prefer the target page's own title over its slug, so prose reads
    // "see Sink contracts", not "see sink-contracts". An explicit alias wins.
    // A same-page [[#Anchor]] has no page part; show the section name
    // rather than a stray '#'.
    const label = (alias || (to && titles.get(to)) ||
                   target.split('#')[0] || target.replace(/^#/, '')).trim()
    return to ? `[${clean(label)}](#${WIKI_PREFIX}${to})` : `**${clean(label)}**`
  })

  return (
    <div className="markdown-doc fade-in">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith('#' + WIKI_PREFIX)) {
              const to = href.slice(1 + WIKI_PREFIX.length)
              return (
                <a href={href}
                   onClick={e => { e.preventDefault(); onNavigate(to) }}
                   style={{ cursor: 'pointer' }}>{children}</a>
              )
            }
            return /^https?:\/\//.test(href || '')
              ? <a href={href} target="_blank" rel="noreferrer">{children}</a>
              // A repo-relative path cannot resolve inside the SPA; showing it
              // as dead text beats a link that goes nowhere useful.
              : <span className="md-deadlink">{children}</span>
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

export default function Docs() {
  const { data: guides, isLoading } = useGuides()
  const [active, setActive] = useState(null)

  const { tree, byStem, titles, home } = useMemo(() => {
    const tree = new Map(SECTIONS.map(s => [s.key, []]))
    const byStem = new Map()
    const titles = new Map()
    let home = null
    for (const g of guides || []) {
      const { section, stem } = split(g.name)
      if (HIDDEN.has(stem)) continue
      byStem.set(stem, g.name)
      titles.set(g.name, g.title)
      if (!section) { if (stem === 'index') home = g.name; continue }
      if (tree.has(section)) tree.get(section).push({ ...g, stem })
    }
    for (const [key, items] of tree) {
      const lead = FIRST[key]
      items.sort((a, b) =>
        (a.stem === lead ? -1 : b.stem === lead ? 1 : 0) ||
        a.title.localeCompare(b.title))
    }
    return { tree, byStem, titles, home }
  }, [guides])

  const current = active || home
  if (isLoading) return <div style={{ padding: 24 }}><Spinner size={16} /></div>
  if (!guides?.length) return (
    <>
      <PageTitle>Docs</PageTitle>
      <PageSub>No <code>docs/</code> directory found next to this project.</PageSub>
    </>
  )

  return (
    <>
      <PageTitle>Docs</PageTitle>
      <PageSub>
        The handbook — readable here, versioned in <code>docs/</code>, and an
        Obsidian vault if you open the folder.
      </PageSub>

      <div style={{ display: 'flex', gap: 28, alignItems: 'flex-start', marginTop: 20 }}>
        <nav style={{
          flex: '0 0 232px', position: 'sticky', top: 20,
          maxHeight: 'calc(100vh - 40px)', overflowY: 'auto', paddingBottom: 20,
        }}>
          {home && (
            <button onClick={() => setActive(home)}
              style={navItemStyle(current === home)}>Overview</button>
          )}
          {SECTIONS.map(s => {
            const items = tree.get(s.key) || []
            if (!items.length) return null
            return (
              <div key={s.key} style={{ marginTop: 18 }}>
                <div style={{
                  fontSize: 11, fontWeight: 700, letterSpacing: '.06em',
                  textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 2,
                }}>{s.label}</div>
                <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 7, opacity: .8 }}>
                  {s.blurb}
                </div>
                {items.map(g => (
                  <button key={g.name} onClick={() => setActive(g.name)}
                    style={navItemStyle(current === g.name)} title={clean(g.title)}>
                    {clean(g.title)}
                  </button>
                ))}
              </div>
            )
          })}
        </nav>

        <div style={{
          // Prose reads badly at full width; cap the measure the way the
          // rendered artifacts do, and keep the column left-aligned.
          flex: 1, minWidth: 0, maxWidth: '76ch', background: 'var(--card)',
          border: '1px solid var(--border)', borderRadius: 10,
          padding: '22px 30px',
        }}>
          {current
            ? <Reader name={current} byStem={byStem} titles={titles}
                      onNavigate={setActive} />
            : <div style={{ color: 'var(--muted)', fontSize: 13 }}>Pick a page.</div>}
        </div>
      </div>
    </>
  )
}

function navItemStyle(isActive) {
  return {
    display: 'block', width: '100%', textAlign: 'left',
    padding: '5px 9px', marginBottom: 1, borderRadius: 6,
    border: '1px solid transparent', cursor: 'pointer',
    fontFamily: 'inherit', fontSize: 12.5, lineHeight: 1.35,
    background: isActive ? 'var(--blue)' : 'transparent',
    color: isActive ? '#fff' : 'var(--text)',
    whiteSpace: 'normal',
  }
}
