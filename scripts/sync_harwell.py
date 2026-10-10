"""Render Harwell's docs/ into this site's harwell/ and its Harwell tab.

harwell-project/harwell docs/ is the source; harwell/ here is its output and
is never edited by hand. Each run replaces harwell/ whole and rewrites the
Harwell tab of docs.json, so a page added, renamed or deleted upstream is
added, renamed or deleted here.

    python scripts/sync_harwell.py <harwell checkout> [<harwell commit>]

What a page becomes: its first H1 is the frontmatter title (Mintlify renders
the title), the paragraph under it the description (llms.txt lists it), HTML
comments go (MDX refuses them), a link to another docs page points at its page
here with the anchor Mintlify gives the heading GitHub's anchor named, and a link to anything else in the repository points at GitHub.

The tab: one group per Diataxis directory, in the order below; within a group,
pages in the order docs/index.md first links them, then by name.
"""
from __future__ import annotations

import json
import posixpath
import re
import shutil
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
OUT = "harwell"
TAB = "Harwell"
REPO_URL = "https://github.com/harwell-project/harwell"
GROUPS = (
    ("Getting started", ("index.md", "tutorial.md")),
    ("Guides", ("guides/",)),
    ("Reference", ("reference/",)),
    ("Explanation", ("explanation/",)),
)
# After Hum's and Kennet's tabs: Harwell is the newest product on the site.
TAB_AFTER = "Kennet"

LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")
COMMENT = re.compile(r"<!--.*?-->\n?", re.S)
FENCE = re.compile(r"^(```|~~~)")


def page_id(rel: str) -> str:
    """docs/<rel>.md -> the page path under this site."""
    stem = rel[: -len(".md")]
    return f"{OUT}/{stem}"


def github_slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", plain(heading).lower()).replace(" ", "-")


def mintlify_slug(heading: str) -> str:
    text = plain(heading).lower().replace("'", "\u2019")
    return re.sub(r"-+", "-", re.sub(r"[.\s]+", "-", text)).strip("-")


def anchors(source: str) -> dict[str, str]:
    """A page's GitHub heading anchors -> the anchors Mintlify gives them."""
    found: dict[str, str] = {}

    def collect(prose: str) -> str:
        for heading in re.findall(r"^#{1,6} +(.+?)\s*$", prose, re.M):
            found[github_slug(heading)] = mintlify_slug(heading)
        return prose

    outside_fences(source, collect)
    return found


def rewrite_link(target: str, rel: str, ref: str, slugs: dict[str, dict[str, str]]) -> str:
    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
        return target
    path, _, anchor = target.partition("#")
    resolved = posixpath.normpath(posixpath.join("docs", posixpath.dirname(rel), path or posixpath.basename(rel)))
    if resolved.startswith("docs/") and resolved.endswith(".md"):
        page = resolved[len("docs/"):]
        anchor = slugs.get(page, {}).get(anchor, anchor)
        out = "" if not path else "/" + page_id(page)
    else:
        out = f"{REPO_URL}/blob/{ref}/{resolved}"
    return f"{out}#{anchor}" if anchor else out


def outside_fences(text: str, fn) -> str:
    """Apply fn to the prose only, leaving fenced code as written."""
    out, buf, fenced = [], [], False
    for line in text.splitlines(keepends=True):
        if FENCE.match(line.lstrip()):
            if not fenced:
                out.append(fn("".join(buf)))
                buf = []
            else:
                out.append("".join(buf))
                buf = []
            fenced = not fenced
            out.append(line)
            continue
        buf.append(line)
    out.append("".join(buf) if fenced else fn("".join(buf)))
    return "".join(out)


def plain(md: str) -> str:
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", md)
    text = re.sub(r"[*_`]", "", text)
    return " ".join(text.split())


def render(rel: str, source: str, ref: str, slugs: dict[str, dict[str, str]]) -> str:
    lines = source.splitlines()
    title, start = None, 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title, start = line[2:].strip(), i + 1
            break
        if line.strip() and not line.startswith("<!--"):
            break
    if title is None:
        raise SystemExit(f"docs/{rel}: no H1 to take the title from")
    body = "\n".join(lines[start:]) + "\n"
    body = outside_fences(body, lambda s: COMMENT.sub("", s)).lstrip("\n")
    body = outside_fences(
        body, lambda s: LINK.sub(lambda m: m[1] + rewrite_link(m[2], rel, ref, slugs) + m[3], s)
    )
    first = body.split("\n\n", 1)[0]
    front = [f"title: {json.dumps(title)}"]
    if first and not first.startswith(("#", "|", "```", "*", "-", "<")):
        front.append(f"description: {json.dumps(plain(first))}")
    return "---\n" + "\n".join(front) + "\n---\n\n" + body


def nav(pages: list[str], index: str) -> dict:
    order = {}
    for target in LINK.findall(index):
        path = posixpath.normpath(target[1].partition("#")[0])
        order.setdefault(path, len(order))
    groups = []
    for name, prefixes in GROUPS:
        members = [p for p in pages if p.startswith(prefixes) or p in prefixes]
        if name == "Getting started":
            members.sort(key=lambda p: prefixes.index(p) if p in prefixes else len(prefixes))
        else:
            members.sort(key=lambda p: (order.get(p, len(order)), p))
        if members:
            groups.append({"group": name, "pages": [page_id(p) for p in members]})
    placed = {p for g in groups for p in g["pages"]}
    rest = sorted(page_id(p) for p in pages if page_id(p) not in placed)
    if rest:
        groups.append({"group": "More", "pages": rest})
    return {"tab": TAB, "groups": groups}


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    docs = Path(sys.argv[1]) / "docs"
    ref = sys.argv[2] if len(sys.argv) == 3 else "main"
    pages = sorted(p.relative_to(docs).as_posix() for p in docs.rglob("*.md"))
    if "index.md" not in pages:
        raise SystemExit(f"{docs}: no index.md")

    sources = {rel: (docs / rel).read_text(encoding="utf-8") for rel in pages}
    slugs = {rel: anchors(text) for rel, text in sources.items()}
    out = SITE / OUT
    shutil.rmtree(out, ignore_errors=True)
    for rel in pages:
        dest = out / (rel[: -len(".md")] + ".md")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render(rel, sources[rel], ref, slugs), encoding="utf-8")

    config_path = SITE / "docs.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    tabs = [t for t in config["navigation"]["tabs"] if t.get("tab") != TAB]
    names = [t.get("tab") for t in tabs]
    at = names.index(TAB_AFTER) + 1 if TAB_AFTER in names else len(tabs)
    tabs.insert(at, nav(pages, (docs / "index.md").read_text(encoding="utf-8")))
    config["navigation"]["tabs"] = tabs
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(pages)} pages from {docs} at {ref}")


if __name__ == "__main__":
    main()
