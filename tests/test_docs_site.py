"""
The static docs site under ``site/docs/`` is generated, and stays generated.

``site/`` deploys to any static host with no build step — that is what makes
the marketing site trivial to host — so the rendered HTML is committed rather
than built at deploy time. The cost of committing generated output is drift:
someone edits ``docs/*.md``, the markdown and the published page disagree, and
nothing says so.

These tests are what says so. The first re-runs the generator into a temp
directory and compares it byte-for-byte with what is committed, the site and
the generated ``docs/index.md`` alike; editing the vault or ``docs/toc.yaml``
without running ``python site/build_docs.py`` fails here. The rest pin the
properties the generator exists to provide.
"""

from __future__ import annotations

import filecmp
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SITE_DOCS = REPO / "site" / "docs"
BUILDER = REPO / "site" / "build_docs.py"

pytestmark = pytest.mark.skipif(
    not BUILDER.is_file(), reason="the docs-site generator is not present"
)


def _built(tmp_path: Path) -> Path:
    """Run the generator against a copy of site/ and docs/, return its docs
    output. docs/ is copied, not linked: the generator writes docs/index.md."""
    pytest.importorskip("markdown")
    import shutil

    site = tmp_path / "site"
    site.mkdir()
    shutil.copy(REPO / "site" / "index.html", site / "index.html")
    shutil.copy(BUILDER, site / "build_docs.py")
    # The generator resolves docs/ as a sibling of site/.
    shutil.copytree(REPO / "docs", tmp_path / "docs")

    r = subprocess.run([sys.executable, str(site / "build_docs.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return site / "docs"


def _tree(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


class TestGeneratedSiteIsCurrent:
    def test_regenerating_produces_no_diff(self, tmp_path):
        """Edit docs/*.md without re-running the generator and this fails.

        The fix is always the same: ``python site/build_docs.py``.
        """
        fresh = _built(tmp_path)
        committed, generated = _tree(SITE_DOCS), _tree(fresh)

        missing = sorted(generated - committed)
        extra = sorted(committed - generated)
        assert not missing, (
            f"site/docs is missing {missing} — run: python site/build_docs.py")
        assert not extra, (
            f"site/docs has stale pages {extra} — run: python site/build_docs.py")

        differing = [
            rel for rel in sorted(generated)
            if not filecmp.cmp(fresh / rel, SITE_DOCS / rel, shallow=False)
        ]
        assert not differing, (
            f"site/docs is out of date with docs/*.md in {differing} — "
            f"run: python site/build_docs.py"
        )
        assert filecmp.cmp(fresh.parent.parent / "docs" / "index.md",
                           REPO / "docs" / "index.md", shallow=False), (
            "docs/index.md is out of date with docs/toc.yaml — "
            "run: python site/build_docs.py")


class TestSiteProperties:
    def test_every_vault_page_is_in_the_toc_and_published(self):
        """docs/toc.yaml is the one order the site, the app and the index
        read. A page it does not list is a page nobody finds; an entry with no
        page is a dead link in all three."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location("build_docs", BUILDER)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        toc = mod.load_toc()

        listed = {f"{s['key']}/{e['page']}" for s in toc["sections"] for e in s["pages"]}
        for entry in sorted(listed):
            assert (REPO / "docs" / f"{entry}.md").is_file(), (
                f"docs/toc.yaml lists {entry}, but docs/{entry}.md does not exist")
            assert (SITE_DOCS / f"{entry}.html").is_file(), (
                f"docs/{entry}.md is not published — run: python site/build_docs.py")
        for md in (REPO / "docs").rglob("*.md"):
            rel = md.relative_to(REPO / "docs").with_suffix("").as_posix()
            if md.stem in mod.HIDDEN:
                assert not list(SITE_DOCS.rglob(f"{md.stem}.html")), (
                    f"{md.stem} is an internal document and must not publish")
                continue
            if rel == "index" or rel in toc["moved"]:
                continue                      # the generated home; a kept stub
            assert rel in listed, (
                f"docs/{rel}.md is not in docs/toc.yaml — add it to a section")

    def test_every_moved_address_still_lands(self):
        """A page that changed folder keeps its old address on the site: a
        forwarding page to where it went."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location("build_docs", BUILDER)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        for old, new in mod.load_toc()["moved"].items():
            assert (REPO / "docs" / f"{new}.md").is_file(), f"{old} moved to a missing {new}"
            stub = (SITE_DOCS / f"{old}.html").read_text(encoding="utf-8")
            assert f'url=../{new}.html' in stub, f"{old}.html does not forward to {new}"

    def test_the_positioning_doc_never_ships(self):
        """north-star.md is gitignored and internal. If it ever reaches the
        public site it is a leak, not a formatting problem."""
        assert not (SITE_DOCS / "north-star.html").exists()
        for page in SITE_DOCS.rglob("*.html"):
            assert "north-star" not in page.read_text(encoding="utf-8")

    def test_pages_carry_no_unrendered_wiki_links(self):
        """A literal [[link]] on the published page means the rewrite missed
        it — the reader gets markup instead of a link."""
        offenders = [
            str(p.relative_to(SITE_DOCS)) for p in SITE_DOCS.rglob("*.html")
            if "[[" in p.read_text(encoding="utf-8")
        ]
        assert not offenders, f"unrendered wiki links in {offenders}"
