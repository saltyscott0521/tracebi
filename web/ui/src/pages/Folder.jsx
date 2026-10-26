import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { useMe, useModels, usePipelines, useRole, useRuns, useStartPipelineRun } from '../api'
import { CoverFan, CoverTile, Health } from '../components/Directory'
import { useDocumentTitle } from '../components/Layout'
import { NotFound } from '../components/Scope'
import { Btn, BtnLink, CopyCommand, Empty, SkeletonCard, Time, useToast } from '../components/Shared'
import { KINDS, hueStyle, kindOf, newestBuild, reportLabel, useBuilds, useLibrary } from '../folders'
import { askPath, mayUse, modelPath, pipelineBelongsToModel, reportPagePath, transformPath } from '../nav'
import { count, plural } from '../format'
import { stamp } from '../when'

const YOU_CAN = {
  publish: 'You can publish here',
  request: 'You can ask to publish here',
}

/**
 * What the person may do in a folder, and (to a manager, or the owner of a
 * personal folder) who holds what there. Permissions are edited in the
 * folder's _folder.yaml: the app only shows them.
 */
export function FolderNote({ info }) {
  const p = info.permissions
  const can = YOU_CAN[info.mode] || 'View only'
  return (
    <div className="lfolder__note">
      <div>
        {can}.
        {info.mine && ' Only you see this folder unless you share it by file.'}
        {info.personal && !info.mine && ' Shared with you by its owner.'}
        {info.accepts === 'checkable' && ' It accepts only reports whose every number a query can re-run.'}
      </div>
      {p && (
        <div style={{ marginTop: 6 }}>
          {p.malformed
            ? <div>The folder file cannot be read, so nobody but admins is granted anything.</div>
            : Object.keys(p.grants).length === 0
              ? <div>{info.mine
                ? 'Nobody else is granted anything.'
                : 'No folder file applies, so roles decide.'}</div>
              : (
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {Object.entries(p.grants).map(([level, who]) => (
                    <li key={level}><span style={{ textTransform: 'capitalize' }}>{level}</span>: {who.join(', ')}</li>
                  ))}
                </ul>
              )}
          <div style={{ color: 'var(--muted)' }}>
            {p.file ? <>From <code>{p.file}</code>. </> : null}
            Permissions are changed in the folder&rsquo;s <code>_folder.yaml</code> file. Editing them here is not
            available yet.
          </div>
        </div>
      )}
    </div>
  )
}

const MONTH = { month: 'long' }

// The folder's builds, oldest to newest: one bar per recorded build of its
// reports (the run store's last twelve), the newest marked, a failed one
// marked as failed. A build row stores no verdict, so the caption counts
// builds and failures and claims nothing about whether the older ones
// reproduced.
function BuildTimeline({ items }) {
  const { data } = useRuns(['report_build', 'background_run'])
  const names = new Set(items.map(r => r.name))
  const runs = (data || []).filter(r => names.has(r.target)).slice(0, 12).reverse()
  if (runs.length < 2) return null
  const failed = runs.filter(r => ['failed', 'error', 'refused'].includes(r.status)).length
  const since = new Date(runs[0].started).toLocaleString('en-US', MONTH)
  const caption = `${count(runs.length, 'build')} since ${since} · ${failed ? `${failed} failed` : 'none failed'}`
  return (
    <figure className="ftimeline">
      <div className="ftimeline__bars" role="img" aria-label={caption}>
        {runs.map((r, i) => (
          <i key={r.id} title={`${reportLabel({ name: r.target, display_name: r.display_name })}, ${stamp(r.started)}`}
             className={[i === runs.length - 1 && 'is-newest', failed && ['failed', 'error', 'refused'].includes(r.status) && 'is-failed']
               .filter(Boolean).join(' ') || undefined} />
        ))}
      </div>
      <figcaption className="ftimeline__cap">
        <span>{caption}</span><span>{stamp(runs[runs.length - 1].started)}</span>
      </figcaption>
    </figure>
  )
}

/**
 * One folder's page (/?folder=<path>): its hero (what it holds, its newest
 * covers, and what to do with it), its builds, its health, its
 * reports by kind and who may do what in it. A folder the person may not see
 * is a page that does not exist, as for one that does not.
 */
export default function FolderPage({ path }) {
  const library = useLibrary()
  const { desk, builds, verdictFor } = useBuilds()
  const { data: modelList } = useModels()
  const { data: pipelines } = usePipelines()
  const { data: me } = useMe()
  const role = useRole()
  const navigate = useNavigate()
  const toast = useToast()
  const { hash } = useLocation()
  const { mutate: start, isPending } = useStartPipelineRun()
  const [making, setMaking] = useState(false)
  const folder = library.byPath[path]
  useDocumentTitle(folder?.label, 'Reports')

  // The rail's Dashboards and Pages rows open the section of that name.
  useEffect(() => {
    if (folder && hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' })
  }, [folder, hash])

  if (library.loading) return <SkeletonCard />
  if (!folder) return <NotFound />

  const models = (modelList || []).filter(m => folder.models.includes(m.name))
  const one = models.length === 1 ? models[0] : null
  const items = folder.items
  const newest = newestBuild(items, builds)
  const tables = models.reduce((n, m) => n + m.tables.length, 0)
  const measures = models.reduce((n, m) => n + m.measures.length, 0)
  const lead = items.find(r => /(^|\/|_)showcase$/.test(r.name))
    || items.find(r => r.name === newest?.report) || items[0]
  // Only an admin may run a pipeline (it writes the warehouse); with no
  // sign-in everyone is admin. The same gate as Refresh data on a transform's page.
  const admin = !!me && (!me.role || me.role === 'admin')
  const pipeline = one && admin
    ? (pipelines || []).find(p => p.model === one.name) || (pipelines || []).find(p => pipelineBelongsToModel(p, one.name))
    : null
  const canAuthor = (role === 'analyst' || role === 'admin') && !folder.mine
  const refresh = () => start({ pipeline: pipeline.pipeline }, {
    onSuccess: () => navigate(pipeline.transform ? transformPath(pipeline.transform) : modelPath(one.name)),
    onError: err => toast(`Could not start: ${err.message}`, 'error'),
  })
  const byKind = KINDS.map(([kind, label]) => [kind, label, items.filter(r => kindOf(r) === kind)])
    .filter(([, , list]) => list.length)

  return (
    <div className="folder" style={{ ...hueStyle(folder.hue), '--f': `var(${folder.hue})` }}>
      <nav aria-label="Breadcrumb" className="crumbs">
        <Link to="/">Library</Link> <span aria-hidden="true">›</span> <span aria-current="page">{folder.label}</span>
      </nav>
      <section className="fhero" aria-label={folder.label}>
        <div className="fhero__text">
          <p className="fhero__eyebrow">
            Folder
            {/* The way back to how the numbers are made, for those who see Data. */}
            {models.map(m => (
              <span key={m.name}> · {mayUse(role, 'data')
                ? <Link to={modelPath(m.name)} className="fhero__data">Data › {m.label || m.name}</Link>
                : m.name}</span>
            ))}
          </p>
          <h1 className="display-title">{folder.label}</h1>
          <p className="fhero__lede">
            {folder.mine ? 'Your own folder: only you see it unless you share it by file. '
              : items.length ? `${count(items.length, 'report')} ${plural(items.length, 'reads', 'read')} ${models.map(m => m.label || m.name).join(' and ') || 'this folder'}. `
                : ''}
            {items.length ? 'Every cover is its page as it was last built.' : 'Nothing here yet.'}
          </p>
          {/* What the folder is made of, never a figure: a number appears only inside a report. */}
          <p className="fhero__facts">
            {count(items.length, 'report')}
            {models.length > 0 && <> · {count(tables, 'table')} · {count(measures, 'measure')}</>}
            {newest && <> · last built <Time iso={newest.built_at} /></>}
          </p>
          <div className="fhero__acts">
            {/* A report's name can be long: the button says which one it opens in its title. */}
            {lead && (
              <BtnLink to={reportPagePath(lead.name)} variant="primary" title={reportLabel(lead)}>
                {/(^|\/|_)showcase$/.test(lead.name) ? 'Open the showcase' : 'Open the newest'}
              </BtnLink>
            )}
            {models.slice(0, 3).map(m => (
              <BtnLink key={m.name} to={askPath(m.name)}>{one ? 'Ask this model' : `Ask ${m.label || m.name}`}</BtnLink>
            ))}
            {pipeline && <Btn variant="outline" onClick={refresh} disabled={isPending}>Refresh data</Btn>}
            {canAuthor && (
              <Btn variant="outline" aria-expanded={making} onClick={() => setMaking(m => !m)}>New report</Btn>
            )}
          </div>
          {making && (
            <div className="fhero__new">
              <CopyCommand>{`tracebi new-dashboard "${folder.path}/New dashboard"`}</CopyCommand>
            </div>
          )}
        </div>
        <CoverFan reports={items} builds={builds} className="cstack" />
      </section>
      <BuildTimeline items={items} />
      <Health reports={items} verdictFor={verdictFor} builds={builds} known={!!desk} />
      {!items.length && (
        <Empty title="Nothing here yet"
               body={folder.mine ? 'Publish a draft to My published from Review to put a report here.'
                 : 'A report lands here when one is published into this folder.'} />
      )}
      {byKind.map(([kind, label, list]) => (
        <section key={kind} id={kind} className="fkind" aria-labelledby={`fkind-${kind}`}>
          <h2 id={`fkind-${kind}`} className="fkind__title">{label}</h2>
          <ul className="cgrid">
            {list.map(r => (
              <li key={r.name}><CoverTile report={r} verdict={verdictFor(r)} built={builds[r.name]} /></li>
            ))}
          </ul>
        </section>
      ))}
      {folder.info && (
        <section className="fkind" aria-labelledby="fkind-perm">
          <h2 id="fkind-perm" className="fkind__title">Permissions</h2>
          <FolderNote info={folder.info} />
        </section>
      )}
    </div>
  )
}
