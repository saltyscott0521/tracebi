### Changed — Build mode talks to the report frame by message

- The report frame is sandboxed, so the app can no longer read its DOM. Pointing,
  the change timeline and the flash on changed figures now run in the report
  runtime (`tracebi.js`) and report to the app by `postMessage`. Behaviour is
  the same; the app accepts a message only from the frame's own window.
