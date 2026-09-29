// The one picture of how TraceBi fits together: data moves left to right.
// The sidebar, command palette, the "you are here" strip and Getting Started
// all read this list, so the order and the words are said once.
//
//   where it is kept → how it gets there → what it means → ask it → read it

export const CHAIN = [
  { key: 'sources', folder: 'a connector, declared in models/<name>.py',   path: '/connectors', label: 'Sources',    icon: 'connectors', was: 'Connectors',
    ask: 'Where is the data kept?',
    hint: 'The file, folder or database each model reads from. A source is a connector.' },
  { key: 'pipelines', folder: 'pipelines/ and transforms/', path: '/pipelines',  label: 'Pipelines',  icon: 'pipelines',  was: 'Refresh',
    ask: 'How does it get there?',
    hint: 'Rebuild the data, then the reports that read it.' },
  { key: 'models', folder: 'models/',    path: '/models',     label: 'Data model', icon: 'models',     was: 'Contract',
    ask: 'What does it mean?',
    hint: 'The tables, how they join, and what every measure is.' },
  { key: 'explore', folder: 'no files: a question',   path: '/explore',    label: 'Explore',    icon: 'explore',
    ask: 'What does it say?',
    hint: 'Ask the model a question and see the query behind the answer.' },
  { key: 'reports', folder: 'reports/<model>/',   path: '/reports',    label: 'Reports',    icon: 'reports',    was: 'Report',
    ask: 'What do people read?',
    hint: 'Pages built on the model. Every figure is a query.' },
]

export const step = key => CHAIN.find(s => s.key === key)
