// The library's folders: one list, in one order, each with one hue, read by
// the rail's folder tree, the directory (/) and a folder's page (/?folder=<path>).
//
// A folder is where a report sits (reports/<folder>/<name>), as the API names
// it: every report the caller may see is in the list, so a folder they may not
// see never is. Their own My published is listed even before it holds anything.
// A top-level folder is a project (one area's reports, named for the model or
// models it reads); a folder inside one stays a folder, and My published is a
// person's own space, never a project. The address stays /?folder=<path>.
//
// The hue is a label, never a state: verdicts keep their own chip and colours.
// Six hue tokens (--hue-1 … --hue-6, global.css) go to the folders in the
// order of their paths, so a folder keeps its hue however the list is sorted;
// My published takes the accent.

import { useMemo } from 'react'

import { useDesk, useFolders, useModels, useReports, useRole } from './api'
import { folderOf, reportModels } from './nav'
import { verdictOf } from './verdict'

export const HUES = 6
const MINE_HUE = '--accent-text'

/** The CSS variable that is *path*'s hue, among *folders* ({path, mine}). */
export function folderHue(path, folders = []) {
  if (folders.find(f => f.path === path)?.mine) return MINE_HUE
  const shared = [...new Set(folders.filter(f => !f.mine).map(f => f.path))].sort()
  return `--hue-${(Math.max(shared.indexOf(path), 0) % HUES) + 1}`
}

/** Whether a library folder ({path, mine}) is a project: a top-level folder, not My published. */
export const isProject = f => !f.mine && !f.path.includes('/')

/** What a library folder is called: a Project, or a Folder (one inside a project, or My published). */
export const folderWord = f => (isProject(f) ? 'Project' : 'Folder')

/** The style that hands a folder's hue to everything inside it, as --c. */
export const hueStyle = hue => ({ '--c': `var(${hue})` })

/** A folder's page: /?folder=<path>. */
export const folderPath = path => `/?${new URLSearchParams({ folder: path })}`

// What a package draws its page from (the API's made_from) is the kind of
// report it is: an app.jsx is a dashboard, a template.html a page.
export const KINDS = [['dashboards', 'Dashboards'], ['pages', 'Pages'], ['other', 'Other']]
export const kindOf = r => ({ 'app.jsx': 'dashboards', 'template.html': 'pages' })[r.made_from] || 'other'
export const KIND_TAG = { dashboards: 'Dashboard', pages: 'Page' }

/** A report's own name, as people read it. */
export const reportLabel = r => r.display_name || r.name.slice(r.name.lastIndexOf('/') + 1)

/**
 * Every folder the caller may see, sorted by label with My published last:
 * `{path, label, mine, info, items, kinds, models, hue}`. *info* is the folder's
 * row in /api/folders (its permissions), when it has one; *kinds* counts its
 * reports by kind. Also `all` (every report), `top` (those in no folder),
 * `mine` (the caller's My published, or null) and `byPath`.
 */
export function useLibrary() {
  const { data: reports, isLoading } = useReports()
  const { data: folderData, isLoading: foldersLoading } = useFolders()
  const { data: modelList } = useModels()
  const role = useRole()
  return useMemo(() => {
    const all = reports || []
    const models = modelList || []
    // A viewer cannot publish, so has no My published to fill.
    const mine = role === 'analyst' || role === 'admin' ? folderData?.personal || null : null
    const info = Object.fromEntries((folderData?.folders || []).map(f => [f.path, f]))
    const paths = new Set(all.map(r => folderOf(r.name)).filter(Boolean))
    if (mine) paths.add(mine)
    const label = path => (path === mine ? 'My published'
      : models.find(m => m.name === path)?.label || path.split('/').join(' / '))
    const folders = [...paths].map(path => {
      const items = all.filter(r => folderOf(r.name) === path)
      const kinds = {}
      items.forEach(r => { kinds[kindOf(r)] = (kinds[kindOf(r)] || 0) + 1 })
      const read = [...new Set(items.flatMap(reportModels))]
      const named = models.some(m => m.name === path) ? [path] : []
      return {
        path, label: label(path), mine: path === mine, info: info[path], items, kinds,
        models: (read.length ? read : named).filter(m => models.some(x => x.name === m)),
      }
    }).sort((a, b) => (a.mine - b.mine) || a.label.localeCompare(b.label))
    folders.forEach(f => { f.hue = folderHue(f.path, folders) })
    return {
      // Until the reports, the folders and the role are known, nothing is
      // said to be missing.
      all, folders, mine, loading: isLoading || foldersLoading || role === null,
      top: all.filter(r => !folderOf(r.name)),
      byPath: Object.fromEntries(folders.map(f => [f.path, f])),
    }
  }, [reports, folderData, modelList, role, isLoading, foldersLoading])
}

/**
 * What the desk says of *reports*: each one's last build (`builds`, by name),
 * its verdict (`verdictFor`, null before the desk answers: nothing is claimed
 * yet), and the newest build among them (`newest`).
 */
export function useBuilds() {
  const { data: desk } = useDesk()
  return useMemo(() => {
    const builds = Object.fromEntries((desk?.builds || []).map(b => [b.report, b]))
    const verdictFor = r => (desk ? verdictOf({ report: r, build: builds[r.name] }) : null)
    return { desk, builds, verdictFor }
  }, [desk])
}

/** The newest build among *reports*, or null. */
export function newestBuild(reports, builds) {
  return reports.map(r => builds[r.name]).filter(b => b?.built_at)
    .sort((a, b) => b.built_at.localeCompare(a.built_at))[0] || null
}
