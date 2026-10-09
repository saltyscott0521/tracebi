### Fixed — leaving Build mode always stops pointing

- Clicking a figure and then leaving Build mode sent "pointing at" and
  "stop pointing" as two independent requests. When the stop landed first,
  the server kept the pointer and an agent went on resolving "this" to a
  figure nobody was looking at. The app now sends pointing updates one at a
  time, in order (one TanStack Query mutation scope).
