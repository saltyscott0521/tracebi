import { Link, useParams } from 'react-router-dom'

import { useLive } from '../api'
import { PageTitle, PageSub, Empty, Card } from '../components/Shared'
import { Exhibit } from '../components/Workbench'
import { when } from '../components/Attention'
import { reportPagePath } from '../nav'

// A private watch link: what one agent, connected over MCP, is doing right
// now. The agent hands the person this address (get_context's `watch`); no
// menu leads here, and nothing lists other sessions.
export default function Live() {
  const { watch } = useParams()
  const { events, error } = useLive(watch)

  if (error?.status === 404) {
    return (
      <>
        <PageTitle>No such watch link</PageTitle>
        <PageSub>Check the address your agent gave you. A link lasts as long as its session.</PageSub>
      </>
    )
  }
  return (
    <>
      <PageTitle>Watching your agent</PageTitle>
      <PageSub>
        What your agent does over MCP appears here as it works, newest first: the queries
        it runs and the reports it builds. This link is private to its session. Anyone you
        give it to can watch.
      </PageSub>
      <div className="live-status" role="status">
        <span className="live-status__dot" aria-hidden="true" />
        {error ? 'Reconnecting…' : events.length ? `Live · last update ${when(events[0].at)}` : 'Live · waiting for your agent'}
      </div>
      {events.length === 0
        ? <Empty message="Nothing yet. Ask your agent a question: its queries and builds appear here as it goes." />
        : (
          <Card>
            <div className="wb wb--project">
              {events.map(ev => (
                <div key={ev.seq}>
                  <Exhibit ex={ev} />
                  {ev.report && (
                    <Link className="live-open" to={reportPagePath(ev.report)}>Open {ev.report} →</Link>
                  )}
                </div>
              ))}
            </div>
          </Card>
        )}
    </>
  )
}
