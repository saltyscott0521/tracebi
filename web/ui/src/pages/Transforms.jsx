import { Link, useSearchParams } from 'react-router-dom'

import { useMe, usePipelines, useStartPipelineRun, useTransforms } from '../api'
import { useModelLabel } from '../components/Scope'
import CodeView from '../components/CodeView'
import { FORM_LABEL } from '../chain'
import { count } from '../format'
import { dataPath, pipelineModels, transformsPath } from '../nav'
import { Badge, Btn, Card, CardTitle, Empty, ErrorDetail, SkeletonList, Time, useToast } from '../components/Shared'

// Data's Transforms tab (/data/transforms): every file in transforms/, one row
// each: its form, the models it feeds (through the pipeline that runs it, or
// the tables its certificate says it wrote), how many tables it wrote, the
// file its checks are declared in, and when it last wrote. Its name opens the
// model's Transform tab when a model is known; otherwise the file itself, here
// (?file=<name>). An admin may run the pipeline that runs it, the same run as
// that model's Refresh data. ?model=<m> keeps only what feeds that model.

// Start the pipeline that runs a transform: Refresh data, from this list.
function RunButton({ pipeline, model }) {
  const toast = useToast()
  const { mutate: start, isPending } = useStartPipelineRun()
  const run = () => start({ pipeline }, {
    onSuccess: res => toast(res.already_running
      ? 'Already running. Its log is on the model’s Transform tab.'
      : 'Started. Its log is on the model’s Transform tab.', 'info'),
    onError: err => toast(`Could not start: ${err.message}`, 'error'),
  })
  return (
    <Btn size="sm" variant="outline" disabled={isPending} onClick={run}
         title={`Run pipeline ${pipeline}${model ? `, which refreshes ${model}` : ''}`}>
      Run
    </Btn>
  )
}

export default function Transforms() {
  const [params, setParams] = useSearchParams()
  const model = params.get('model') || ''
  const open = params.get('file') || ''
  const { data, isLoading, error } = useTransforms()
  const { data: pipelines } = usePipelines()
  const { data: me } = useMe()
  const admin = !!me && (!me.role || me.role === 'admin')
  const labelOf = useModelLabel()

  if (isLoading) return <SkeletonList />
  if (error) return <ErrorDetail error={error} />
  const rows = (data || []).filter(t => !model || t.models.includes(model))
  // The model a transform's name opens: the one its pipeline refreshes, else
  // the first that reads what it wrote.
  const homeOf = t => {
    const p = (pipelines || []).find(x => t.pipelines.includes(x.pipeline))
    return (p && pipelineModels(p)[0]) || t.models[0] || ''
  }
  const shown = rows.find(t => t.name === open)
  const show = name => setParams(p => { p.set('file', name); return p }, { replace: true })

  return (
    <>
      {model && (
        <p className="scope-note">
          Only what feeds {labelOf(model)}. <Link to={transformsPath()}>Show every transform</Link>
        </p>
      )}
      {rows.length === 0 ? (
        <Empty message={model
          ? 'No transform feeds this model: no pipeline runs one for it, and no certificate names one.'
          : 'No transforms yet. Write one with tracebi new-transform, in transforms/.'} />
      ) : (
        <div className="whlist">
          <table className="tb-list transforms">
            <thead>
              <tr>
                <th scope="col">Transform</th>
                <th scope="col">Form</th>
                <th scope="col">Feeds</th>
                <th scope="col" className="num">Tables</th>
                <th scope="col">Checks</th>
                <th scope="col">Last wrote</th>
                {admin && <th scope="col"><span className="sr-only">Actions</span></th>}
              </tr>
            </thead>
            <tbody>
              {rows.map(t => {
                const home = homeOf(t)
                return (
                  <tr key={t.name} data-transform={t.name}>
                    <td>
                      {home
                        ? <Link to={dataPath(home, 'transform')}><code>{t.name}</code></Link>
                        : <button type="button" className="linklike" aria-pressed={open === t.name}
                                  onClick={() => show(t.name)}><code>{t.name}</code></button>}
                    </td>
                    <td><Badge>{FORM_LABEL[t.form] || t.form}</Badge></td>
                    <td>
                      {t.models.length
                        ? t.models.map((m, i) => <span key={m}>{i > 0 && ', '}<Link to={dataPath(m)}>{labelOf(m)}</Link></span>)
                        : <span className="wb-meta">no model</span>}
                    </td>
                    <td className="num" title={t.tables.join(', ') || undefined}>
                      {t.tables.length ? `writes ${count(t.tables.length, 'table')}` : <span className="wb-meta">none recorded</span>}
                    </td>
                    <td title={t.note || undefined}>
                      {t.contract_file ? <code>{t.contract_file.split('/').pop()}</code> : <span className="wb-meta">no contract</span>}
                    </td>
                    <td><Time iso={t.written_at} relative fallback={<span className="wb-meta">never, here</span>} /></td>
                    {admin && (
                      <td className="num">
                        {t.pipelines[0] && <RunButton pipeline={t.pipelines[0]} model={home} />}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {shown && (
        <Card className="transforms__code">
          <CardTitle action={<Btn size="sm" variant="outline" onClick={() => setParams(p => { p.delete('file'); return p }, { replace: true })}>Close</Btn>}>
            <code>{shown.file}</code>
          </CardTitle>
          <CodeView kind="transforms" name={shown.name} />
        </Card>
      )}
    </>
  )
}
