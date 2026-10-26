import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { useModel } from '../api'
import TheLine, { useLineFacts } from '../components/TheLine'
import { checksWords, refreshWords } from '../words'
import EditAsDraft from '../components/EditAsDraft'
import { ModelDetail } from './Models'
import { DataFrame } from './Data'
import { askPath, modelsPath, transformPath } from '../nav'
import { BtnLink, useToast } from '../components/Shared'

// What changed on the line when a run ends: every station may read differently.
const AFTER_A_RUN = ['pipelines', 'history', 'warehouse', 'warehouses', 'desk', 'reports', 'models', 'model']

/**
 * A model's page (/data/models/<m>): Data › Models › its name, where it is
 * defined, the line (its one way to the other stages), then the data browser
 * with the Semantic layer as its summary. The model page is the model: its
 * transform, sources and runs are pages of their own, one station away.
 */
function ModelPage({ model }) {
  const facts = useLineFacts(model)
  const { transform } = facts
  const { data: detail } = useModel(model)
  const toast = useToast()
  const qc = useQueryClient()
  const label = detail?.label || model
  const file = transform.pipeline?.transform

  // A refresh started elsewhere (its transform's page, the folder) changes
  // what every station says; a toast says how it ended.
  const was = useRef(false)
  useEffect(() => {
    if (was.current && !transform.running) {
      AFTER_A_RUN.forEach(key => qc.invalidateQueries({ queryKey: [key] }))
      toast(transform.failed ? 'The refresh failed. Its transform’s page says why.' : `Refreshed ${label}.`,
        transform.failed ? 'error' : 'info')
    }
    was.current = transform.running
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transform.running])

  return (
    <DataFrame trail={[[modelsPath(), 'Models']]} here={label}>
      <div className="overview">
        <header className="overview__head">
          <h1 className="overview__title">{label} {label !== model && <span className="overview__id">{model}</span>}</h1>
          {/* A question is about one model, so it is asked from here (or its folder). */}
          <div className="overview__acts"><BtnLink to={askPath(model)}>Ask this model</BtnLink></div>
          {detail?.source_file && <p className="overview__sub">Defined in <code>{detail.source_file}</code></p>}
        </header>

        {transform.failed && (
          <p role="status" className="overview__alert">
            <strong>
              <span aria-hidden="true">✕</span> {refreshWords({ failedAt: transform.lastAt }).text}
              {transform.failure && <>: {checksWords({ failed: transform.failure.failed }).text}</>}.
            </strong>
            {transform.failure && facts.builtCount > 0 && <span>The built reports were made from the tables it replaced.</span>}
            {file && <Link to={transformPath(file)}>See why</Link>}
          </p>
        )}

        <TheLine model={model} line={facts.line} />

        <section className="stage" aria-label="Model">
          <ModelDetail name={model} action={<EditAsDraft kind="models" path={model} bare />} />
        </section>
      </div>
    </DataFrame>
  )
}

export default ModelPage
