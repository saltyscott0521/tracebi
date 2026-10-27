import { createContext, useContext, useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { useHealth, useAppStatus, useMe, useRole, signOut } from '../api'
import { page, placesFor, placeOf, mayUse, SIDEBAR_FOLDERS, dataFolder, folderOf } from '../nav'
import { KINDS, folderPath, hueStyle, useBuilds, useLibrary, newestBuild } from '../folders'
import { count } from '../format'
import { stamp } from '../when'
import { useScope, useOpenReport, NavMenuContext, NotForYou } from './Scope'
import { SkeletonCard } from './Shared'
import CommandPalette from './CommandPalette'
import { BrandMark } from './Art'

const ICONS = {
  reports: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5M9 13h7M9 17h5" />
    </svg>
  ),
  data: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="4" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="20" cy="12" r="2" /><path d="M6 12h4M14 12h4" />
    </svg>
  ),
  review: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
    </svg>
  ),
  workflow: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M3 4.5A1.5 1.5 0 014.5 3h2A1.5 1.5 0 018 4.5v2A1.5 1.5 0 016.5 8h-2A1.5 1.5 0 013 6.5v-2zM12 13.5a1.5 1.5 0 011.5-1.5h2a1.5 1.5 0 011.5 1.5v2a1.5 1.5 0 01-1.5 1.5h-2a1.5 1.5 0 01-1.5-1.5v-2z" />
      <path fillRule="evenodd" d="M6 8.5a.5.5 0 01.5.5v2a2 2 0 002 2h3a.5.5 0 010 1h-3a3 3 0 01-3-3V9a.5.5 0 01.5-.5z" clipRule="evenodd" />
    </svg>
  ),
  docs: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
    </svg>
  ),
}

// The browser tab's title names the page, so tabs, history and bookmarks can
// be told apart: "Portfolio Dashboard · TraceBi", "Warehouse · Data · TraceBi".
// By default it is the page's own h1, after the tab inside a place when the
// address names one. A page whose h1 is not what it is called (a table, a
// model's view) names itself with useDocumentTitle instead.
const TitleContext = createContext(null)

/**
 * Name the browser tab while this component is mounted: *parts* joined by
 * " · ", most specific first, then "TraceBi". Empty parts are dropped;
 * with none, the default (the page's h1) applies.
 * `useDocumentTitle('fact_holdings', 'Warehouse')` → "fact_holdings · Warehouse · TraceBi".
 */
export function useDocumentTitle(...parts) {
  const name = useContext(TitleContext)
  const text = parts.filter(Boolean).join(' · ')
  useEffect(() => {
    if (!name || !text) return undefined
    name(text)
    return () => name(null)
  }, [name, text])
}

// The tab a place's address names, in the words its tab row uses (Review's),
// or nothing on the place's first tab. Data has no tabs: its folder is said
// after the page's h1 (see the title effect in Layout).
function tabWords(scope) {
  if (page(scope.page)?.parent) return page(scope.page).label
  return ''
}

// What an h1 says, without the small print some carry (a model's identifier
// beside its label): its own text, else all of it.
function headingWords(h1) {
  if (!h1) return ''
  const own = [...h1.childNodes].filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent).join('')
  return (own.trim() || h1.textContent).replace(/\s+/g, ' ').trim()
}

function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clipRule="evenodd" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
      <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
    </svg>
  )
}

function NavItem({ path, label, icon, active, onNavigate, n }) {
  return (
    <li>
      <Link
        to={path}
        onClick={onNavigate}
        aria-current={active ? 'page' : undefined}
        className="nav-link"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '8px 12px',
          margin: '0 8px',
          borderRadius: 'var(--radius)',
          color: active ? 'var(--sidebar-text-active)' : 'var(--sidebar-text)',
          textDecoration: 'none',
          fontSize: 'var(--text-caption)',
          fontWeight: active ? 500 : 400,
          background: active ? 'var(--sidebar-active)' : 'transparent',
        }}
      >
        <span style={{
          width: 15, height: 15,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
          opacity: active ? 1 : 0.85,
          color: active ? 'var(--sidebar-accent)' : 'inherit',
        }}>
          {ICONS[icon]}
        </span>
        {label}
        {n != null && <span className="tree__n">{n}</span>}
      </Link>
    </li>
  )
}

// The sidebar's library: All reports, then a row per folder the person may
// see (its hue, its count), and under the open one its Dashboards and Pages.
// The folder you are in is the current entry: on its page, on one of its
// reports, or asking its model.
function FolderTree({ library, current, onNavigate }) {
  return (
    <ul className="tree" aria-labelledby="tree-library">
      {library.folders.map(f => {
        const on = f.path === current
        return (
          <li key={f.path}>
            <Link to={folderPath(f.path)} onClick={onNavigate} className="tree__folder" style={hueStyle(f.hue)}
                  aria-current={on ? 'page' : undefined}>
              <i aria-hidden="true" /><span className="tree__label">{f.label}</span>
              <span className="tree__n">{f.items.length}</span>
            </Link>
            {on && KINDS.some(([k]) => f.kinds[k]) && (
              <ul className="tree__subs">
                {KINDS.filter(([k]) => f.kinds[k]).map(([k, label]) => (
                  <li key={k}>
                    <Link to={`${folderPath(f.path)}#${k}`} onClick={onNavigate} className="tree__sub">{label} · {f.kinds[k]}</Link>
                  </li>
                ))}
              </ul>
            )}
          </li>
        )
      })}
    </ul>
  )
}

// Data in the workshop: its own row (the home), then its four lists nested
// under it in the library tree's styling, always shown (they are Data's
// structure, not a filter). Each opens its list, as a console's left nav does.
// The folder an address sits in is the current entry at any depth
// (/data/warehouse/fact_holdings marks Warehouse); Data itself is current on
// its home and on Lineage. No hue: a hue labels a library folder.
function DataTree({ item, folder, onNavigate }) {
  const inside = SIDEBAR_FOLDERS.some(f => f.key === folder)
  return (
    <>
      <NavItem {...item} active={item.active && !inside} onNavigate={onNavigate} />
      <li>
        <ul className="tree__subs" aria-label="Data">
          {SIDEBAR_FOLDERS.map(f => (
            <li key={f.key}>
              <Link to={f.path} onClick={onNavigate} className="tree__sub"
                    aria-current={f.key === folder ? 'page' : undefined}>{f.label}</Link>
            </li>
          ))}
        </ul>
      </li>
    </>
  )
}

// The live line at the sidebar's foot: when the newest build was made, and
// whether every built report still reproduces (the desk's re-check), or how
// many need a look. The dot pulses, except under reduced motion.
function LiveLine({ library }) {
  const { desk, builds, verdictFor } = useBuilds()
  const newest = newestBuild(library.all, builds)
  if (!desk || !newest) return null
  const states = library.all.filter(r => builds[r.name]).map(r => verdictFor(r).state)
  const off = states.filter(s => s === 'needs-a-look' || s === 'does-not-reproduce').length
  const all = states.length && states.every(s => s === 'reproduces')
  return (
    <p className="liveline" role="status">
      <span className={`liveline__dot${off ? ' liveline__dot--warn' : all ? '' : ' liveline__dot--quiet'}`} aria-hidden="true" />
      <span>
        Built {stamp(newest.built_at)} · {off ? `${off} need${off === 1 ? 's' : ''} a look`
          : all ? `all ${states.length} reproduce` : count(states.length, 'build')}
      </span>
    </p>
  )
}

// A page of its own (an open report) keeps the app's nav as a 56px rail: the
// same places, icon only, each with a name and a tooltip. "Expand the menu"
// opens the full sidebar over the page; on a phone the rail is hidden and the
// page's own Menu button does the same.
function Rail({ items, expanded, onExpand }) {
  return (
    <nav aria-label="Main" className="rail" aria-hidden={expanded || undefined} inert={expanded}>
      <div className="rail__brand"><BrandMark /></div>
      {items.map(item => (
        <Link key={item.path} to={item.path} className="rail__item" aria-label={item.label}
              aria-current={item.active ? 'page' : undefined}>
          <span className="rail__ico">{ICONS[item.icon]}</span>
          <span className="rail__tip" aria-hidden="true">{item.label}</span>
        </Link>
      ))}
      <span className="rail__fill" />
      <button type="button" className="rail__item" aria-label="Expand the menu"
              aria-expanded={!!expanded} onClick={onExpand}>
        <span className="rail__ico">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
               strokeLinecap="round" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
        </span>
        <span className="rail__tip" aria-hidden="true">Expand the menu</span>
      </button>
    </nav>
  )
}

export default function Layout({ children }) {
  const [open, setOpen] = useState(false)
  const { data: health, isSuccess: healthOk } = useHealth()
  const version = healthOk && typeof health?.version === 'string' ? health.version : ''
  const { data: appStatus } = useAppStatus()
  const update = appStatus?.update?.available ? appStatus.update : null
  const { data: me } = useMe()
  const role = useRole()
  const person = me?.sign_in === 'oidc' && me.actor ? me : null
  // Follow the OS until the viewer picks one; their pick is remembered, the OS
  // default is not (so it keeps following the OS).
  const [dark, setDark] = useState(() => {
    try {
      const saved = localStorage.getItem('tracebi-theme')
      if (saved) return saved === 'dark'
    } catch { /* private window */ }
    return !!window.matchMedia?.('(prefers-color-scheme: dark)').matches
  })
  const [chose, setChose] = useState(() => {
    try { return !!localStorage.getItem('tracebi-theme') } catch { return false }
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    if (chose) { try { localStorage.setItem('tracebi-theme', dark ? 'dark' : 'light') } catch { /* ignore */ } }
  }, [dark, chose])

  const close = () => setOpen(false)
  const openerRef = useRef(null)
  const closeRef = useRef(null)
  const scope = useScope()
  const places = placesFor(role)
  const place = places.find(p => p.key === placeOf(scope.page))
  const openReport = useOpenReport()
  const { pathname, search } = useLocation()
  const [named, setNamed] = useState(null)
  const library = useLibrary()
  // The folder you are in: its page, one of its reports, or Ask of its model.
  const query = new URLSearchParams(search)
  const current = pathname === '/' ? query.get('folder')
    : openReport ? folderOf(openReport.name)
      : scope.page === 'ask' ? library.folders.find(f => f.path === query.get('model') || f.models.includes(query.get('model')))?.path
        : null

  // The page's h1 arrives after its data does, so the title follows the DOM
  // rather than the route alone.
  useEffect(() => {
    const tab = tabWords(scope)
    const write = () => {
      const h1 = document.querySelector('.layout-main h1, .rail-shell__page h1')
      // Under Data: the page's h1, then its folder, then Data ("fact_holdings ·
      // Warehouse · Data"; a folder's own page says its name once).
      const parts = named ? [named]
        : scope.page === 'data' ? [headingWords(h1), dataFolder(scope.tab)?.label, 'Data']
          : [tab, headingWords(h1)]
      const next = [...new Set([...parts.filter(Boolean), 'TraceBi'])].join(' · ')
      if (document.title !== next) document.title = next
    }
    write()
    if (named) return undefined
    const watch = new MutationObserver(write)
    watch.observe(document.getElementById('root') || document.body, { childList: true, subtree: true, characterData: true })
    return () => watch.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [named, pathname])

  // While the mobile menu is open, the page behind it stays put.
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  // Over a report the full menu is an overlay: focus goes into it, Escape closes
  // it (before the report's own panel hears the key), and focus goes back to
  // what opened it.
  const wasOpen = useRef(false)
  useEffect(() => {
    if (!openReport) return undefined
    if (open) {
      wasOpen.current = true
      closeRef.current?.focus()
      const esc = e => { if (e.key === 'Escape') { e.stopPropagation(); close() } }
      document.addEventListener('keydown', esc, true)
      return () => document.removeEventListener('keydown', esc, true)
    }
    if (wasOpen.current) {
      wasOpen.current = false
      if (openerRef.current?.isConnected) openerRef.current.focus()
    }
    return undefined
  }, [open, openReport])
  // The opener is the clicked button (a click does not focus a button in every browser).
  const openMenu = e => { openerRef.current = e?.currentTarget || document.activeElement; setOpen(true) }

  // The places this role sees. Each marks itself current on every page inside
  // it, but for the library, where the folder you are in is current when
  // there is one (the rail of an open report keeps Reports).
  const items = places.map(p => ({ path: p.path, label: p.label, icon: p.key, active: placeOf(scope.page) === p.key }))
  const inFolder = !!current && library.folders.some(f => f.path === current)
  // An address above the role is a plain page saying so (while the role loads,
  // nothing of it is drawn).
  const body = scope.page && !mayUse(role, scope.page)
    ? (role === null ? <SkeletonCard /> : <NotForYou role={page(scope.page).minRole} />)
    : children

  return (
    <TitleContext.Provider value={setNamed}>
    <div style={openReport ? undefined : { display: 'flex', minHeight: '100vh' }}
         className={openReport ? 'rail-shell' : undefined}>
      <CommandPalette />

      {/* Mobile top bar */}
      {!openReport && <header className="mobile-header" style={{
        display: 'none', position: 'fixed', top: 0, left: 0, right: 0,
        height: 52,
        background: 'var(--header-bg)',
        borderBottom: '1px solid var(--border)',
        alignItems: 'center', justifyContent: 'space-between', padding: '0 16px',
        zIndex: 200,
      }}>
        {/* On a phone the header says which of the four places you are in. */}
        <span style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <BrandMark />
          <span style={{ fontSize: 'var(--text-wordmark)', fontWeight: 600, color: 'var(--text)', letterSpacing: '-0.01em', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            TraceBi
            {place && <span className="mobile-header__place">{place.label}</span>}
          </span>
        </span>
        <button onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          display: 'flex', flexDirection: 'column', gap: 5,
          padding: 0, width: 44, height: 44,
          alignItems: 'center', justifyContent: 'center',
        }}>
          {[0,1,2].map(i => (
            <span key={i} style={{ display: 'block', width: 20, height: 2, background: 'var(--text-2)', borderRadius: 1 }} />
          ))}
        </button>
      </header>}

      {/* Overlay */}
      {open && (
        <div onClick={close} style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,.4)',
          zIndex: 250,
        }} />
      )}

      {/* An open report keeps the nav as a rail; the sidebar opens over it. */}
      {openReport && <Rail items={items} expanded={open} onExpand={openMenu} />}

      {/* Sidebar */}
      {/* Pinned top AND bottom, not min-height: 100vh — on a phone, 100vh is
          not the visible screen (browser bars, zoom), and the drawer stopped
          short. It scrolls itself if the links outgrow a short screen. */}
      {(!openReport || open) && <nav aria-label="Main" style={{
        width: 'var(--nav-w)',
        background: 'var(--sidebar-bg)',
        borderRight: '1px solid var(--sidebar-border)',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
        position: 'fixed', top: 0, bottom: 0, left: 0, zIndex: 300,
        overflowY: 'auto', overscrollBehavior: 'contain',
      }} className={`app-nav${open ? ' nav-open' : ''}${openReport ? ' app-nav--overlay' : ''}`}>

        <button
          ref={closeRef}
          className="nav-close-btn"
          onClick={close}
          style={{
            display: 'none',
            position: 'absolute', top: 10, right: 10,
            background: 'var(--sidebar-field)',
            border: '1px solid var(--sidebar-field-border)',
            borderRadius: 'var(--radius)', width: 32, height: 32,
            alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer',
            color: 'var(--sidebar-text)', fontSize: 'var(--text-lg)', lineHeight: 1,
            zIndex: 1,
          }}
          aria-label="Close menu"
        >×</button>

        {/* Brand */}
        <div style={{ padding: '22px 20px 16px', borderBottom: '1px solid var(--sidebar-border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <BrandMark />
            <div style={{ fontSize: 'var(--text-wordmark)', fontWeight: 600, color: 'var(--sidebar-text-active)', letterSpacing: '-0.01em', lineHeight: 1.2 }}>
              TraceBi
            </div>
          </div>
          <button
            onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
            style={{
              width: '100%',
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--sidebar-field)', border: '1px solid var(--sidebar-field-border)',
              borderRadius: 'var(--radius)', padding: '7px 10px', cursor: 'pointer',
              color: 'var(--sidebar-text)', fontSize: 'var(--text-sm)', fontFamily: 'inherit',
              transition: 'background .15s',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
            </svg>
            Jump to anything…
            <kbd style={{
              marginLeft: 'auto', fontSize: 'var(--text-eyebrow)', padding: '1px 5px',
              background: 'var(--sidebar-field)', border: '1px solid var(--sidebar-field-border)',
              borderRadius: 'var(--radius-sm)', color: 'var(--sidebar-text)',
            }}>⌘K</kbd>
          </button>
        </div>

        {/* The library as a folder tree (All reports, then each folder), then
            the workshop: Data and Review for the roles that use them, and Docs
            (the handbook) for everyone, last. A model is a folder's, and a
            filter inside a place, not the frame of the app. */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0 4px' }}>
          <p className="tree__sec" id="tree-library">Library</p>
          <ul style={{ listStyle: 'none' }}>
            {items.filter(item => item.icon === 'reports').map(item => (
              <NavItem key={item.path} {...item} label="All reports" n={library.all.length}
                       active={item.active && !inFolder} onNavigate={close} />
            ))}
          </ul>
          <FolderTree library={library} current={current} onNavigate={close} />
          {items.some(item => item.icon !== 'reports') && <p className="tree__sec" id="tree-workshop">Workshop</p>}
          <ul style={{ listStyle: 'none' }} aria-labelledby="tree-workshop">
            {items.filter(item => item.icon !== 'reports').map(item => (item.icon === 'data'
              ? <DataTree key={item.path} item={item} folder={scope.page === 'data' ? scope.tab : null} onNavigate={close} />
              : <NavItem key={item.path} {...item} onNavigate={close} />))}
          </ul>
        </div>
        <LiveLine library={library} />

        {/* The foot: which TraceBi this is, whether a newer one is out, and
            the theme. The handbook is a place now (Docs, above). */}
        <div style={{
          padding: '12px 16px 14px',
          borderTop: '1px solid var(--sidebar-border)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {version ? (
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--sidebar-text)' }}>v{version}</span>
            ) : null}
            {update && (
              <a href={update.url || '#'} target="_blank" rel="noreferrer"
                 title={`TraceBi ${update.latest} is available. To update this ${update.kind} install:\n${update.command}\n\n(or run: tracebi update)`}
                 style={{
                   fontSize: 'var(--text-eyebrow)', fontWeight: 600, color: 'var(--sidebar-accent)', textDecoration: 'none',
                   border: '1px solid var(--sidebar-field-border)', borderRadius: 999,
                   padding: '1px 7px', whiteSpace: 'nowrap',
                 }}>
                v{update.latest} available
              </a>
            )}
            <button
              onClick={() => { setChose(true); setDark(d => !d) }}
              title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              style={{
                marginLeft: 'auto', background: 'var(--sidebar-field)',
                border: '1px solid var(--sidebar-field-border)', borderRadius: 'var(--radius-sm)',
                color: 'var(--sidebar-text)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 26, height: 26, flexShrink: 0, transition: 'background .15s',
              }}
            >
              {dark ? <SunIcon /> : <MoonIcon />}
            </button>
          </div>
          {person && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, fontSize: 'var(--text-sm)', color: 'var(--sidebar-text)' }}>
              <span title={`${person.actor} (${person.role})`}
                    style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {person.actor}
              </span>
              <button onClick={signOut} style={{
                marginLeft: 'auto', flexShrink: 0, background: 'none', cursor: 'pointer',
                border: '1px solid var(--sidebar-field-border)', borderRadius: 'var(--radius-sm)',
                color: 'var(--sidebar-text)', fontSize: 'var(--text-xs)', padding: '2px 8px', fontFamily: 'inherit',
              }}>Sign out</button>
            </div>
          )}
        </div>
      </nav>}

      {/* Main content */}
      {openReport ? (
        <NavMenuContext.Provider value={{ open: openMenu }}>
          <div className="rail-shell__page" inert={open}>{children}</div>
        </NavMenuContext.Provider>
      ) : (
        <main style={{
          marginLeft: 'var(--nav-w)', flex: 1, minWidth: 0,
          padding: '36px 44px', maxWidth: 1340,
        }} className="layout-main">
          {body}
        </main>
      )}

      {!openReport && <style>{`
        @media (max-width: 860px) {
          .mobile-header { display: flex !important; }
          .nav-close-btn { display: flex !important; }
          .app-nav { transform: translateX(-100%); transition: transform .18s ease; }
          .app-nav.nav-open { transform: translateX(0); }
          main { margin-left: 0 !important; margin-top: 52px; padding: 20px 16px !important; max-width: 100% !important; }
        }
      `}</style>}
    </div>
    </TitleContext.Provider>
  )
}
