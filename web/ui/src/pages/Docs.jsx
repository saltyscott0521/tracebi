import { useState, useMemo, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { useGuides, useGuide } from '../api'
import { docPath } from '../nav'
import { PageTitle, PageSub, Spinner, useNarrow } from '../components/Shared'
import GettingStarted from './GettingStarted'

// docs/ is a vault: pages live under concepts/, guides/, reference/ and
// architecture/, and the API addresses a subdirectory page as "dir--stem".
// The sidebar rebuilds that tree, in reading order — a visitor should meet
// the ideas before the look-up tables.
// docs/architecture/ (design notes for changing the framework) is not listed:
// a reader meets it only through a link from a page that cites it.
const SECTIONS = [
  { key: 'concepts',     label: 'Concepts',     blurb: 'The ideas. Read once.' },
  { key: 'guides',       label: 'Guides',       blurb: 'Task-shaped walkthroughs.' },
  { key: 'reference',    label: 'Reference',    blurb: 'Look things up.' },
  { key: 'agents',       label: 'Agent SOPs',   blurb: 'Standard operating procedures.' },
  { key: 'strategy',     label: 'Strategy',     blurb: 'Where TraceBi is going, and why.' },
]

// Internal working documents that ship in a source checkout but are not
// product documentation. The positioning doc is gitignored outright; the
// roadmap is a control document, not a guide. A retired page stays in docs/
// as a stub (old wiki links keep resolving in the vault) but is not listed.
const HIDDEN = new Set(['north-star', 'ROADMAP', 'receipts'])

// A retired page's stem → the page that replaced it: a wiki link to it, and
// its old address, open the new one.
const MOVED = { receipts: 'trace' }

// Get started is the handbook's first page: the app's own walkthrough, not a
// file in docs/, at /docs/get-started.
const GET_STARTED = 'get-started'

// A distinctive fragment prefix, so a genuine in-page #anchor in the markdown
// is never mistaken for a cross-reference.
const WIKI_PREFIX = 'tb-doc:'

// Within a section, lead with the page that orients you.
const FIRST = { concepts: 'the-three-phase-workflow', guides: 'plain-english', strategy: 'vision-and-positioning' }

const clean = t => (t || '').replace(/`/g, '')

// A page's own "# Title" is the page's h1, above the card, so the markdown
// starts below it. Only a "# " line before any other text is taken.
const withoutTitle = text => text.replace(/^\s*# .*\n?/, '')

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
  const content = withoutTitle(data.content).replace(/\[\[([^\]]+)\]\]/g, (whole, inner) => {
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
          // The page's h1 is the document's title; a second "# " is the next level.
          h1: ({ children }) => <h2 className="md-h1">{children}</h2>,
          // A long code block scrolls sideways: a keyboard must reach it.
          pre: ({ node, ...props }) => <pre tabIndex={0} {...props} />,
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
              // A path from the server's root (/api-docs) is served beside the app.
              : href?.startsWith('/') && !href.startsWith('//') ? <a href={href}>{children}</a>
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

/** The page an address under /docs names: home, Get started, or "section--stem". */
function addressed(pathname) {
  const rest = pathname.replace(/^\/docs\/?/, '').replace(/\/+$/, '')
  if (!rest) return null
  if (rest === GET_STARTED) return GET_STARTED
  return rest.replace('/', '--')
}

export default function Docs() {
  const { data: guides, isLoading } = useGuides()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const narrow = useNarrow('(max-width: 820px)')
  // On a phone the sidebar is 31 links between the reader and the first word,
  // so it collapses to a disclosure that closes again after a tap.
  const [navOpen, setNavOpen] = useState(false)

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
    for (const [old, now] of Object.entries(MOVED)) {
      if (byStem.has(now)) byStem.set(old, byStem.get(now))
    }
    for (const [key, items] of tree) {
      const lead = FIRST[key]
      items.sort((a, b) =>
        (a.stem === lead ? -1 : b.stem === lead ? 1 : 0) ||
        a.title.localeCompare(b.title))
    }
    return { tree, byStem, titles, home }
  }, [guides])

  const asked = addressed(pathname)
  const current = asked || home
  const open = name => navigate(docPath(name))
  if (isLoading) return <div style={{ padding: 24 }}><Spinner size={16} /></div>
  // A retired page's address opens the page that replaced it.
  const stem = asked && asked !== GET_STARTED ? asked.split('--').pop() : null
  if (stem && MOVED[stem] && byStem.has(stem)) return <Navigate to={docPath(byStem.get(stem))} replace />
  const known = !asked || asked === GET_STARTED || titles.has(asked)
  // The handbook's home is "Docs"; any other page is its own title, under a
  // "Docs" crumb back to the home.
  const atHome = !asked || asked === home
  const title = atHome ? 'Docs'
    : asked === GET_STARTED ? 'Get started'
      : known ? clean(titles.get(asked)) : 'No page at this address'

  return (
    <>
      {!atHome && <div className="page-header__scope"><Link to={docPath()}>Docs</Link></div>}
      <PageTitle>{title}</PageTitle>
      {atHome && (
        <PageSub>
          The handbook: readable here, versioned in <code>docs/</code>, and an
          Obsidian vault if you open the folder.
        </PageSub>
      )}

      <div style={{
        display: 'flex', gap: narrow ? 14 : 28, marginTop: 20,
        flexDirection: narrow ? 'column' : 'row', alignItems: 'stretch',
      }}>
        {narrow && (
          <button onClick={() => setNavOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              width: '100%', padding: '10px 13px', borderRadius: 8, cursor: 'pointer',
              background: 'var(--card)', border: '1px solid var(--border)',
              color: 'var(--text)', font: 'inherit', fontSize: 13.5, fontWeight: 600,
            }}>
            Docs menu
            <span style={{ color: 'var(--muted)', fontSize: 11 }}>
              {navOpen ? '▲' : '▼'}
            </span>
          </button>
        )}
        <nav style={narrow ? {
          display: navOpen ? 'block' : 'none',
          background: 'var(--card)', border: '1px solid var(--border)',
          borderRadius: 8, padding: '8px 8px 12px',
          maxHeight: '60vh', overflowY: 'auto',
        } : {
          flex: '0 0 232px', position: 'sticky', top: 20,
          maxHeight: 'calc(100vh - 40px)', overflowY: 'auto', paddingBottom: 20,
        }}
          onClick={e => { if (narrow && e.target.closest('a')) setNavOpen(false) }}>
          <Link to={docPath(GET_STARTED)} style={navItemStyle(current === GET_STARTED)}
                aria-current={current === GET_STARTED ? 'page' : undefined}>Get started</Link>
          {home && (
            <Link to={docPath()} style={navItemStyle(current === home)}
                  aria-current={current === home ? 'page' : undefined}>Overview</Link>
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
                <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 7 }}>
                  {s.blurb}
                </div>
                {items.map(g => (
                  <Link key={g.name} to={docPath(g.name)} style={navItemStyle(current === g.name)}
                        aria-current={current === g.name ? 'page' : undefined} title={clean(g.title)}>
                    {clean(g.title)}
                  </Link>
                ))}
              </div>
            )
          })}
        </nav>

        {current === GET_STARTED ? (
          // Get started carries its own cards and code blocks: no card around it.
          <div style={{ flex: 1, minWidth: 0, maxWidth: 880 }}><GettingStarted /></div>
        ) : (
          <div style={{
            // Prose reads badly at full width; cap the measure the way the
            // rendered artifacts do, and keep the column left-aligned.
            flex: 1, minWidth: 0, maxWidth: '76ch', background: 'var(--card)',
            border: '1px solid var(--border)', borderRadius: 10,
            padding: narrow ? '16px 15px 22px' : '22px 30px',
            overflowWrap: 'anywhere',
          }}>
            {!guides?.length
              ? <div style={{ color: 'var(--muted)', fontSize: 13 }}>No <code>docs/</code> directory found next to this project.</div>
              : !known
                ? <div style={{ color: 'var(--muted)', fontSize: 13 }}>There is no page at this address. Pick one from the list.</div>
                : current
                  ? <Reader name={current} byStem={byStem} titles={titles} onNavigate={open} />
                  : <div style={{ color: 'var(--muted)', fontSize: 13 }}>Pick a page.</div>}
          </div>
        )}
      </div>
    </>
  )
}

function navItemStyle(isActive) {
  return {
    display: 'block', width: '100%', textAlign: 'left', textDecoration: 'none', boxSizing: 'border-box',
    padding: '5px 9px', marginBottom: 1, borderRadius: 6,
    border: '1px solid transparent', cursor: 'pointer',
    fontFamily: 'inherit', fontSize: 12.5, lineHeight: 1.35,
    background: isActive ? 'var(--ink)' : 'transparent',
    color: isActive ? 'var(--on-ink)' : 'var(--text)',
    whiteSpace: 'normal',
  }
}
