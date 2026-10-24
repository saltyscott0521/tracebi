import { useState, useMemo, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { useGuides, useGuide } from '../api'
import { docPath, GET_STARTED } from '../nav'
import { PageTitle, PageSub, Spinner, useNarrow } from '../components/Shared'

// docs/ is a vault: pages live under start/, concepts/, guides/, reference/
// and agents/, and the API addresses a subdirectory page as "dir--stem". The
// API lists them in the handbook's order (docs/toc.yaml, the file the docs
// site reads too), with the old address of every page that moved, so the
// sidebar keeps no order of its own. The one thing it adds: the quickstart
// lives at /docs/get-started (nav.js GET_STARTED).

// A distinctive fragment prefix, so a genuine in-page #anchor in the markdown
// is never mistaken for a cross-reference.
const WIKI_PREFIX = 'tb-doc:'

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

/** The page an address under /docs names: home (null) or "section--stem". */
function addressed(pathname) {
  const rest = pathname.replace(/^\/docs\/?/, '').replace(/\/+$/, '')
  if (!rest) return null
  if (rest === 'get-started') return GET_STARTED
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

  const { sections, moved, byStem, titles, home } = useMemo(() => {
    const sections = guides?.sections || []
    const moved = guides?.moved || {}
    const byStem = new Map()
    const titles = new Map()
    const home = guides?.home?.name || null
    if (home) { byStem.set('index', home); titles.set(home, guides.home.title) }
    for (const s of sections) {
      for (const g of s.pages) {
        byStem.set(split(g.name).stem, g.name)
        titles.set(g.name, g.title)
      }
    }
    // A wiki link to a page that moved (receipts → trace) opens its new place.
    for (const [old, now] of Object.entries(moved)) {
      const stem = split(old).stem
      if (!byStem.has(stem)) byStem.set(stem, now)
    }
    return { sections, moved, byStem, titles, home }
  }, [guides])

  const asked = addressed(pathname)
  const current = asked || home
  const open = name => navigate(docPath(name))
  if (isLoading) return <div style={{ padding: 24 }}><Spinner size={16} /></div>
  // An old address opens the page that replaced it, and a page with a short
  // address of its own (Get started) is opened there.
  if (asked && moved[asked]) return <Navigate to={docPath(moved[asked])} replace />
  if (asked && titles.has(asked) && pathname.replace(/\/+$/, '') !== docPath(asked)) {
    return <Navigate to={docPath(asked)} replace />
  }
  const known = !asked || titles.has(asked)
  // The handbook's home is "Docs"; any other page is its own title, under a
  // "Docs" crumb back to the home.
  const atHome = !asked || asked === home
  const title = atHome ? 'Docs'
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
        <nav aria-label="Docs pages" style={narrow ? {
          display: navOpen ? 'block' : 'none',
          background: 'var(--card)', border: '1px solid var(--border)',
          borderRadius: 8, padding: '8px 8px 12px',
          maxHeight: '60vh', overflowY: 'auto',
        } : {
          flex: '0 0 232px', position: 'sticky', top: 20,
          maxHeight: 'calc(100vh - 40px)', overflowY: 'auto', paddingBottom: 20,
        }}
          onClick={e => { if (narrow && e.target.closest('a')) setNavOpen(false) }}>
          {home && (
            <Link to={docPath()} style={navItemStyle(current === home)}
                  aria-current={current === home ? 'page' : undefined}>Overview</Link>
          )}
          {sections.map(s => {
            if (!s.pages.length) return null
            return (
              <div key={s.key} style={{ marginTop: 18 }}>
                <div style={{
                  fontSize: 11, fontWeight: 700, letterSpacing: '.06em',
                  textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 2,
                }}>{s.title}</div>
                {s.blurb && (
                  <div style={{ fontSize: 11.5, color: 'var(--muted)', marginBottom: 7 }}>
                    {s.blurb}
                  </div>
                )}
                {s.pages.map(g => (
                  <Link key={g.name} to={docPath(g.name)} style={navItemStyle(current === g.name)}
                        aria-current={current === g.name ? 'page' : undefined} title={clean(g.title)}>
                    {clean(g.title)}
                  </Link>
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
          padding: narrow ? '16px 15px 22px' : '22px 30px',
          overflowWrap: 'anywhere',
        }}>
          {!sections.length && !home
            ? <div style={{ color: 'var(--muted)', fontSize: 13 }}>No <code>docs/</code> directory found next to this project.</div>
            : !known
              ? <div style={{ color: 'var(--muted)', fontSize: 13 }}>There is no page at this address. Pick one from the list.</div>
              : current
                ? <Reader name={current} byStem={byStem} titles={titles} onNavigate={open} />
                : <div style={{ color: 'var(--muted)', fontSize: 13 }}>Pick a page.</div>}
        </div>
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
