### Fixed

- On a phone, the menu could stop partway down the screen with the page showing
  underneath. The cause was a page wider than the phone: the mobile grid rules
  used plain `1fr` columns, which won't shrink below a wide table's minimum
  width. The Contract page with a table preview open measured 498px on a 375px
  screen, so iOS zoomed the page out and the menu no longer reached the bottom.
  - Every mobile grid now uses `minmax(0, 1fr)`.
  - The Ask page's builder-and-results grid, which had no phone layout at all,
    now stacks.
  - The menu is pinned to the top and bottom of the screen instead of
    `min-height: 100vh`, and scrolls itself if needed.
  - The page behind the open menu no longer scrolls.

  Every page now measures exactly the phone's width.
