"""Render each product's own docs into this site.

sources.json names the sources: each product's docs live in its own repository
beside its code, and this site renders them. A source's pages land under
<name>/ and its tab in docs.json is generated; neither is edited by hand. Each
run replaces both whole, so a page added, renamed or deleted at the source is
added, renamed or deleted here.

    python scripts/sync_docs.py <checkouts>

<checkouts>/<name>/ holds the source's `path` at the commit
<checkouts>/<name>.sha names (.github/workflows/sync-docs.yml fetches both).

What a page becomes: its first H1 is the frontmatter title (Mintlify renders
the title), the paragraph under it the description (llms.txt lists it), HTML
comments go (MDX refuses them), a link to another of the source's pages points
at its page here with the anchor Mintlify gives the heading GitHub's anchor
named, and a link to anything else in the repository points at GitHub at the
source's ref (not the commit, so a commit outside the docs changes nothing here).

The tab: top-level pages first (index, then the order index.md links them),
then one group per directory, Diataxis directories in Diataxis order and any
other directory after them by name. Generated tabs follow the hand-written
ones, in sources.json order.
"""
from __future__ import annotations

import json
import posixpath
import re
import shutil
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
SOURCES = SITE / "sources.json"
FIELDS = {"name", "tab", "repo", "ref", "path"}
DIATAXIS = ("tutorials", "how-to", "guides", "reference", "explanation")
TOP_GROUP = "Getting started"

LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")
COMMENT = re.compile(r"<!--.*?-->\n?", re.S)
FENCE = re.compile(r"^(```|~~~)")
HEADING = re.compile(r"^#{1,6} +(.+?)\s*$", re.M)


def outside_fences(text: str, fn) -> str:
    """Apply fn to the prose only, leaving fenced code as written."""
    out, buf, fenced = [], [], False
    for line in text.splitlines(keepends=True):
        if FENCE.match(line.lstrip()):
            out.append("".join(buf) if fenced else fn("".join(buf)))
            buf, fenced = [], not fenced
            out.append(line)
            continue
        buf.append(line)
    out.append("".join(buf) if fenced else fn("".join(buf)))
    return "".join(out)


def plain(md: str) -> str:
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", md)
    text = re.sub(r"[*_`]", "", text)
    return " ".join(text.split())


def github_slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", plain(heading).lower()).replace(" ", "-")


def mintlify_slug(heading: str) -> str:
    text = plain(heading).lower().replace("'", "’")
    return re.sub(r"-+", "-", re.sub(r"[.\s]+", "-", text)).strip("-")


def anchors(source: str) -> dict[str, str]:
    """A page's GitHub heading anchors -> the anchors Mintlify gives them."""
    found: dict[str, str] = {}

    def collect(prose: str) -> str:
        for heading in HEADING.findall(prose):
            found[github_slug(heading)] = mintlify_slug(heading)
        return prose

    outside_fences(source, collect)
    return found


class Source:
    def __init__(self, entry: dict, checkouts: Path):
        missing = FIELDS - entry.keys()
        if missing:
            raise SystemExit(f"sources.json: {entry.get('name')} lacks {sorted(missing)}")
        self.name, self.tab, self.repo, self.ref = (entry[k] for k in ("name", "tab", "repo", "ref"))
        self.path = entry["path"].strip("/")
        self.docs = checkouts / self.name
        self.sha = (checkouts / f"{self.name}.sha").read_text().strip()
        self.pages = sorted(p.relative_to(self.docs).as_posix() for p in self.docs.rglob("*.md"))
        if "index.md" not in self.pages:
            raise SystemExit(f"{self.repo}/{self.path}: no index.md")
        self.text = {rel: (self.docs / rel).read_text(encoding="utf-8") for rel in self.pages}
        self.slugs = {rel: anchors(text) for rel, text in self.text.items()}

    def page_id(self, rel: str) -> str:
        return f"{self.name}/{rel[: -len('.md')]}"

    def link(self, target: str, rel: str) -> str:
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
            return target
        path, _, anchor = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), path or posixpath.basename(rel)))
        if resolved in self.text:
            anchor = self.slugs[resolved].get(anchor, anchor)
            out = "/" + self.page_id(resolved) if path else ""
        else:
            in_repo = posixpath.normpath(posixpath.join(self.path, resolved))
            out = f"https://github.com/{self.repo}/blob/{self.ref}/{in_repo}"
        return f"{out}#{anchor}" if anchor else out

    def render(self, rel: str) -> str:
        lines = self.text[rel].splitlines()
        title, start = None, 0
        for i, line in enumerate(lines):
            if line.startswith("# "):
                title, start = line[2:].strip(), i + 1
                break
            if line.strip() and not line.startswith("<!--"):
                break
        if title is None:
            raise SystemExit(f"{self.repo}/{self.path}/{rel}: no H1 to take the title from")
        body = "\n".join(lines[start:]) + "\n"
        body = outside_fences(body, lambda s: COMMENT.sub("", s)).lstrip("\n")
        body = outside_fences(body, lambda s: LINK.sub(lambda m: m[1] + self.link(m[2], rel) + m[3], s))
        front = [f"title: {json.dumps(title)}"]
        first = body.split("\n\n", 1)[0]
        if first and not first.startswith(("#", "|", "```", "*", "-", "<")):
            front.append(f"description: {json.dumps(plain(first))}")
        return "---\n" + "\n".join(front) + "\n---\n\n" + body

    def nav(self) -> dict:
        order: dict[str, int] = {}
        for _, target, _ in LINK.findall(self.text["index.md"]):
            order.setdefault(posixpath.normpath(target.partition("#")[0]), len(order))
        by_dir: dict[str, list[str]] = {}
        for rel in self.pages:
            by_dir.setdefault(rel.split("/")[0] if "/" in rel else "", []).append(rel)
        dirs = sorted(by_dir, key=lambda d: (d != "", d not in DIATAXIS,
                                             DIATAXIS.index(d) if d in DIATAXIS else 0, d))
        groups = []
        for d in dirs:
            pages = sorted(by_dir[d], key=lambda p: (p != "index.md", order.get(p, len(order)), p))
            name = TOP_GROUP if d == "" else d.replace("-", " ").capitalize()
            groups.append({"group": name, "pages": [self.page_id(p) for p in pages]})
        return {"tab": self.tab, "groups": groups}

    def write(self) -> None:
        out = SITE / self.name
        shutil.rmtree(out, ignore_errors=True)
        for rel in self.pages:
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(self.render(rel), encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    checkouts = Path(sys.argv[1])
    sources = [Source(e, checkouts) for e in json.loads(SOURCES.read_text())["sources"]]
    config_path = SITE / "docs.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    generated = {s.tab for s in sources}
    tabs = [t for t in config["navigation"]["tabs"] if t.get("tab") not in generated]
    for source in sources:
        source.write()
        tabs.append(source.nav())
        print(f"{source.name}: {len(source.pages)} pages from {source.repo}@{source.sha[:12]}")
    config["navigation"]["tabs"] = tabs
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
