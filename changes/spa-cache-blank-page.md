### Fixed

- A blank page after a deploy. A browser still holding the previous `index.html` asked for the old build's script, and the server answered that missing file with `index.html` (`200 text/html`), which the browser refuses to run. A missing file under the UI is now a 404, `index.html` is served `no-cache` so the next visit picks up a new deploy, and the content-hashed `assets/` files are cached for a year.
