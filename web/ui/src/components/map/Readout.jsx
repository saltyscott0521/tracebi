import { Link } from 'react-router-dom'
import { Verdict } from '../Shared'
import './map.css'

// Under the map: the selection in words (announced when it changes), and the
// key to the drawing. The words carry everything the blue path shows.

export function Readout({ readout }) {
  return (
    <section className="map-readout" aria-live="polite" aria-label="Selection">
      <div className="map-cap">{readout.kind}</div>
      <div className="map-readout__name">{readout.name}</div>
      <p className="map-readout__text">{readout.text}</p>
      {readout.open && <Link to={readout.open} className="map-readout__open">Open report</Link>}
    </section>
  )
}

export function Legend() {
  return (
    <section className="map-legend" aria-label="How to read the map">
      <span><i className="map-key map-key--card" aria-hidden="true" />A card is something you write: a transform, a model, a report</span>
      <span><i className="map-key map-key--pill" aria-hidden="true" />A pill is what gets handed on: files, tables, measures</span>
      <span><i className="map-key map-key--path" aria-hidden="true" />The selected path, with its boxes in bold</span>
      <span><Verdict state="never-built" size="sm" />A report with no page yet; a report&rsquo;s chip says whether its numbers still reproduce</span>
    </section>
  )
}
