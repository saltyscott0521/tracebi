### Security — report frames are sandboxed

- Every frame that shows a report in the web app (the report page, the Reports
  preview, draft previews) now has `sandbox="allow-scripts allow-downloads"`:
  an opaque origin. A report's script can no longer reach `window.parent`, read
  the app's DOM, or call the app's API as the viewer. Before, the frames shared
  the app's origin, so a script could do all three (the report's own
  `connect-src 'none'` did not stop a call made through the parent).
- The share link `/r/<name>` and the workbench and draft preview pages are
  served with `Content-Security-Policy: sandbox allow-scripts allow-downloads`,
  so a report opened on its own runs at an opaque origin too. It combines with
  the report's own CSP; neither loosens the other.
- The app and the report runtime now talk by `postMessage` (frame height, and
  applying a cut from Ask). Messages are accepted only from the frame's own
  window.
