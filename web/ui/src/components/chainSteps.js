// One path per destination.
//
// Sidebar primary: Models only. Open a model; its tabs are the only way into
// Contract / Refresh / Explore / Reports. The report library and sources sit
// in the footer (with Runs), not as peer apps.

/** Primary sidebar — a single destination. */
export const NAV_PRIMARY = [
  { key: 'models', path: '/models', label: 'Models', icon: 'models' },
]

/**
 * Tabs on /models/:name — the only doors into a lineage's surfaces.
 */
export const MODEL_TABS = [
  { key: 'contract', label: 'Contract', ask: 'What does it mean?',
    hint: 'Grain, measures, diagram — the semantic contract.' },
  { key: 'refresh',  label: 'Refresh',  ask: 'How does it get there?',
    hint: 'Run the pipeline that sinks this model\'s tables.' },
  { key: 'explore',  label: 'Explore',  ask: 'What does it say?',
    hint: 'Ask a question and see the query behind the answer.' },
  { key: 'reports',  label: 'Reports',  ask: 'What do people read?',
    hint: 'Packages under reports/<model>/.' },
]

/** Footer destinations — library / setup / ops, not the workspace. */
export const NAV_FOOTER = [
  { path: '/reports',    label: 'All reports' },
  { path: '/connectors', label: 'Sources' },
  { path: '/runs',       label: 'Runs' },
  { path: '/verify',     label: 'Verify a report file' },
]

/**
 * Getting-started story: open a model, then use its tabs.
 */
export const MODEL_STORY = [
  { key: 'contract', label: 'Contract', path: '/models', folder: 'models/',
    ask: 'What does it mean?',
    hint: 'Open a model — grain, keys and measures.' },
  { key: 'refresh',  label: 'Refresh',  path: '/models', folder: 'pipelines/ · transforms/',
    ask: 'How does it get there?',
    hint: 'Same model → Refresh tab.' },
  { key: 'explore',  label: 'Explore',  path: '/models', folder: 'a question, not a file',
    ask: 'What does it say?',
    hint: 'Same model → Explore tab.' },
  { key: 'reports',  label: 'Reports',  path: '/models', folder: 'reports/<model>/',
    ask: 'What do people read?',
    hint: 'Same model → Reports tab, then open one.' },
]

export const CHAIN = MODEL_STORY
export const step = key => MODEL_STORY.find(s => s.key === key)
