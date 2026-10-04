// The app is model-first.
//
// Sidebar: where you stand (Models, Reports, Sources).
// Inside a model: the work surfaces (Contract, Refresh, Explore, Reports).
// The old left-to-right "chain" of five peer pages is gone — that chain is
// now the anatomy of one model, not five destinations.

/** Primary sidebar destinations. */
export const NAV_PRIMARY = [
  { key: 'models',  path: '/models',     label: 'Models',  icon: 'models' },
  { key: 'reports', path: '/reports',    label: 'Reports', icon: 'reports' },
  { key: 'sources', path: '/connectors', label: 'Sources', icon: 'connectors' },
]

/**
 * Tabs on /models/:name — the anatomy of one lineage.
 * Order is the reader's: what it means → refresh → ask → read.
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

/**
 * Getting-started story cards. Paths that live inside a model point at
 * /models (pick one); Sources and the report library are global.
 */
export const MODEL_STORY = [
  { key: 'sources',  label: 'Sources',  path: '/connectors', folder: 'connectors in models/<name>.py',
    ask: 'Where is the data kept?',
    hint: 'The file, folder or database each model reads from.' },
  { key: 'refresh',  label: 'Refresh',  path: '/models', folder: 'pipelines/ and transforms/',
    ask: 'How does it get there?',
    hint: 'Open a model → Refresh to rebuild its warehouse tables.' },
  { key: 'contract', label: 'Contract', path: '/models', folder: 'models/',
    ask: 'What does it mean?',
    hint: 'Open a model to read grain, keys and measures.' },
  { key: 'explore',  label: 'Explore',  path: '/models', folder: 'no files: a question',
    ask: 'What does it say?',
    hint: 'Open a model → Explore to ask it a question.' },
  { key: 'reports',  label: 'Reports',  path: '/reports', folder: 'reports/<model>/',
    ask: 'What do people read?',
    hint: 'The report library. Every figure is a query.' },
]

// Back-compat alias — a few call sites still import CHAIN for the story.
export const CHAIN = MODEL_STORY
export const step = key => MODEL_STORY.find(s => s.key === key)
