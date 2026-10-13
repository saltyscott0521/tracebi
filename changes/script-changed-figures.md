### Added — the receipt says when a script changed a stamped figure

- The report runtime watches every value figure (`data-tb-figure="value"` with
  an `id`). If a custom `script.js` rewrites its text after the runtime wrote
  it, the figure gets `data-tb-script-changed` and its row in the receipt drawer
  reads "changed on the page by a custom script", with the text the receipt
  covers and the text the page shows. The runtime's own later writes (a
  selection) re-stamp first, so they are never flagged. Charts and tables are
  not watched: the runtime redraws them itself as controls move.
