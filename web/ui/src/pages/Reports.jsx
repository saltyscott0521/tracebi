import { useState, useCallback } from 'react'
import ReactFlow, { Background, Controls, Handle, Position } from 'reactflow'
import 'reactflow/dist/style.css'

import { useReports, useRunReport, useReportLineage } from '../api'
import { PageTitle, PageSub, Card, CardTitle, Badge, Spinner, Empty, Btn, Tabs, SplitLayout, ListItem, Alert } from '../components/Shared'

const OP_COLORS = {
  load: '#003366', filter: '#2E7D32', transform: '#F59E0B',
  join: '#E65100', sort: '#6A1B9A', select: '#37474F',
  rename: '#00695C', bronze: '#CD7F32', silver: '#9E9E9E', gold: '#F9A825',
}

function LineageNode({ data }) {
  return (
    <div style={{
      background: data.color || '#333', border: '1px solid rgba(255,255,255,.2)',
      borderRadius: 8, padding: '10px 14px', minWidth: 180, color: '#fff', fontSize: 12,
    }}>
      <Handle type="target" position={Position.Left} style={{ background: 'rgba(255,255,255,.4)' }} />
      <div style={{ fontWeight: 700, textTransform: 'uppercase', fontSize: 10, opacity: .7, marginBottom: 4 }}>
        {data.operation}
      </div>
      <div style={{ lineHeight: 1.4 }}>{data.description}</div>
      {data.metadata?.rows_before != null && (
        <div style={{ marginTop: 6, fontSize: 10, opacity: .6 }}>
          {data.metadata.rows_before} → {data.metadata.rows_after} rows
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ background: 'rgba(255,255,255,.4)' }} />
    </div>
  )
}

const NODE_TYPES = { lineageNode: LineageNode }

function LineageGraph({ graph }) {
  if (!graph?.nodes?.length) return (
    <div style={{ padding: 24, color: 'var(--muted)', fontSize: 13 }}>No lineage data available.</div>
  )
  return (
    <div style={{ height: 340, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)' }}>
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e2d4a" gap={20} />
        <Controls style={{ background: 'var(--card)', border: '1px solid var(--border)' }} />
      </ReactFlow>
    </div>
  )
}

function ReportDetail({ report }) {
  const [tab, setTab] = useState('Output')
  const [result, setResult] = useState(null)
  const [lineageData, setLineageData] = useState(null)
  const { mutate: run, isPending: running, error: runErr } = useRunReport()
  const { mutate: fetchLineage, isPending: loadingLineage } = useReportLineage()

  const handleRun = useCallback(() => {
    run(report.name, {
      onSuccess: (data) => setResult(data),
    })
  }, [report.name, run])

  const handleLineage = useCallback(() => {
    fetchLineage(report.name, {
      onSuccess: (data) => setLineageData(data),
    })
  }, [report.name, fetchLineage])

  if (!report) return <Card><Empty icon="▤" message="Select a report to run it." /></Card>

  return (
    <Card>
      <CardTitle>{report.name}</CardTitle>
      {report.description && (
        <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 16, lineHeight: 1.6 }}>
          {report.description}
        </p>
      )}

      {runErr && <Alert variant="err">{runErr.message}</Alert>}

      {!result && !running && (
        <Btn onClick={handleRun}>▶ Run Report</Btn>
      )}
      {running && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
          <Spinner /> Running report…
        </div>
      )}

      {result && (
        <>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <Btn onClick={handleRun} disabled={running} variant="outline" size="sm">↺ Re-run</Btn>
            {!lineageData && (
              <Btn onClick={handleLineage} disabled={loadingLineage} variant="outline" size="sm">
                {loadingLineage ? <><Spinner size={12} /> Loading…</> : '⊶ View Lineage'}
              </Btn>
            )}
          </div>

          <Tabs
            tabs={lineageData ? ['Output', 'Lineage', 'Manifest'] : ['Output', 'Manifest']}
            active={tab}
            onChange={setTab}
          />

          {tab === 'Output' && (
            <iframe
              srcDoc={result.html}
              style={{ width: '100%', height: 640, border: 'none', borderRadius: 6 }}
              title={report.name}
            />
          )}

          {tab === 'Lineage' && lineageData && (
            <div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>Combined lineage graph</div>
                <LineageGraph graph={lineageData.combined_graph} />
              </div>
              {lineageData.sections?.map(s => (
                <div key={s.section_title} style={{ marginTop: 20 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 8 }}>
                    Section: {s.section_title} · {s.dataset_name}
                  </div>
                  <LineageGraph graph={s.graph} />
                </div>
              ))}
            </div>
          )}

          {tab === 'Manifest' && (
            <pre className="code-block" style={{ maxHeight: 400, overflowY: 'auto' }}>
              {JSON.stringify(result.manifest, null, 2)}
            </pre>
          )}
        </>
      )}
    </Card>
  )
}

export default function Reports() {
  const { data, isLoading } = useReports()
  const [selected, setSelected] = useState(null)
  const reports = data || []

  if (isLoading) return <div style={{ padding: 40 }}><Spinner /></div>

  const current = reports.find(r => r.name === selected)

  return (
    <>
      <PageTitle>Reports</PageTitle>
      <PageSub>{reports.length} report{reports.length !== 1 ? 's' : ''} registered. Select one to run it.</PageSub>

      {reports.length === 0
        ? <Empty icon="▤" message="No reports registered. Add one with @registry.report() in your app module." />
        : (
          <SplitLayout
            left={reports.map(r => (
              <ListItem
                key={r.name}
                selected={selected === r.name}
                onClick={() => setSelected(r.name)}
                name={r.name}
                sub={r.description}
              />
            ))}
            right={<ReportDetail report={current} />}
          />
        )
      }
    </>
  )
}
