#!/usr/bin/env python3
"""Build llama/*.html sub-pages from llama/markdown/*.md (except index.md).

Run after editing any markdown in llama/markdown/. The index page is hand-maintained.

Supports the subset of markdown actually used in this section:
  - # / ## headings
  - paragraphs separated by blank lines
  - *italic*
  - footnote refs [^name] and definitions [^name]: at end of file
  - raw [bracketed editorial notes] are left as-is

Footnotes render as superscript numbers; the definition pops up on click via a
small inline script. Each footnote's text is stored in a <template> and looked
up by key at click time.
"""
from __future__ import annotations

import html
import math
import re
import sys
from collections import Counter
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
LLAMA = ROOT / "llama"
MD_DIR = LLAMA / "markdown"
TEMPLATE = (TOOLS / "templates" / "llama_page.html").read_text(encoding="utf-8")
INDEX_TEMPLATE = (TOOLS / "templates" / "llama_index.html").read_text(encoding="utf-8")

FN_DEF = re.compile(r"^\[\^([\w-]+)\]:[ \t]*(.*)$", re.MULTILINE)
FN_REF = re.compile(r"\[\^([\w-]+)\]")
TIMES = re.compile(r"\{\{times:\s*([^}]+?)\s*\}\}")
STARTERS = re.compile(r"\{\{starters:\s*top10\s*\}\}")

PALETTE_TOP10 = [
    "#b8423a", "#e07a35", "#c89a3a", "#4f7b3c", "#2d8a8a",
    "#3a5a8c", "#6a4a8a", "#a04a7a", "#8a3a3a", "#5a6a4a",
]
PALETTE_RESIDUAL = "#8a7a5a"
ABBREVS = [
    "A.I.", "F. Scott", "vol.", "no.", "pp.",
    "Mr.", "Mrs.", "Dr.", "Ms.", "St.", "Jr.", "Sr.",
    "e.g.", "i.e.", "etc.", "U.S.", "U.K.",
]


def times_in(body: str, phrase: str) -> str:
    pattern = r"\b" + r"\s+".join(re.escape(w) for w in phrase.split()) + r"\b"
    n = len(re.findall(pattern, body, re.IGNORECASE))
    return "once" if n == 1 else f"{n} times"


def sentence_starters(body: str) -> Counter[str]:
    text = body
    text = re.sub(r"(?m)^\[\^[\w-]+\]:.*$", "", text)
    text = re.sub(r"\[\^[\w-]+\]", "", text)
    text = re.sub(r"(?m)^#+\s.*$", "", text)
    text = re.sub(r"(?m)^>", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[[^\]\n]*\]", "", text)
    text = text.replace("**", "").replace("*", "")
    text = (text.replace("“", '"').replace("”", '"')
                .replace("‘", "'").replace("’", "'"))
    text = re.sub(r"\s+", " ", text).strip()
    # Replace dots in abbreviations with the visually identical ONE DOT LEADER
    # (U+2024) so the sentence-splitting regex doesn't treat "e.g." as a boundary.
    for a in ABBREVS:
        text = text.replace(a, a.replace(".", "․"))
    parts = re.split(r"(?<=[.?!])[\"']?\s+", text)
    starters: list[str] = []
    for s in parts:
        s = s.strip().strip("\"'")
        m = re.match(r"([A-Za-z][A-Za-z'\-]*)", s)
        if m:
            starters.append(m.group(1))
    return Counter(starters)


def starters_chart(body: str) -> str:
    counts = sentence_starters(body)
    total = sum(counts.values()) or 1
    top10 = counts.most_common(10)
    rest = total - sum(n for _, n in top10)

    slices = [(w, n, PALETTE_TOP10[i]) for i, (w, n) in enumerate(top10)]
    if rest > 0:
        slices.append(("Mostly singletons", rest, PALETTE_RESIDUAL))

    cx, cy, r = 90, 90, 80
    angle = -math.pi / 2
    paths: list[str] = []
    for _, count, color in slices:
        frac = count / total
        end = angle + frac * 2 * math.pi
        x1, y1 = cx + r * math.cos(angle), cy + r * math.sin(angle)
        x2, y2 = cx + r * math.cos(end), cy + r * math.sin(end)
        large = 1 if frac > 0.5 else 0
        paths.append(
            f'<path d="M {cx},{cy} L {x1:.2f},{y1:.2f} '
            f'A {r},{r} 0 {large} 1 {x2:.2f},{y2:.2f} Z" fill="{color}" />'
        )
        angle = end

    svg = (
        '<svg viewBox="0 0 180 180" width="180" height="180" class="starter-pie" '
        'role="img" aria-label="sentence-starter distribution">'
        + "".join(paths) + "</svg>"
    )

    legend = "".join(
        f'<li><span class="sw" style="background:{color}"></span>'
        f'<span class="lab">{html.escape(label)}</span>'
        f'<span class="num">{count} &middot; {count * 100 / total:.1f}%</span></li>'
        for label, count, color in slices
    )

    return (
        f'<div class="starter-chart">{svg}'
        f'<ul class="starter-legend">{legend}</ul>'
        f'<div class="starter-meta">{total} sentences &middot; '
        f'{len(counts)} unique starters</div></div>'
    )
IMAGE = re.compile(r"!\[([^\]\n]*)\]\(([^)\s]+)\)")
LINKED_IMAGE = re.compile(r"\[!\[([^\]\n]*)\]\(([^)\s]+)\)\]\(([^)\s]+)\)")
LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
ITALIC = re.compile(r"\*([^*\n]+)\*")
# Bare URLs not already inside an href attribute or anchor body.
URL_AUTOLINK = re.compile(r'(?<![">\w/=])(https?://[^\s<>")]+)')


def _autolink_repl(m: re.Match) -> str:
    url = m.group(1)
    trail = ""
    while url and url[-1] in ".,;:!?)":
        trail = url[-1] + trail
        url = url[:-1]
    return f'<a href="{url}">{url}</a>{trail}'


def inline(text: str) -> str:
    text = LINK.sub(r'<a href="\2">\1</a>', text)
    text = URL_AUTOLINK.sub(_autolink_repl, text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = ITALIC.sub(r"<em>\1</em>", text)
    return text


def render_blockquote(block: str) -> str:
    quote_lines: list[str] = []
    cite_lines: list[str] = []
    for line in block.splitlines():
        line = re.sub(r"^>\s?", "", line)
        if line.startswith("*") and not line.startswith("**"):
            line = line.lstrip("*").rstrip("*").strip()
            cite_lines.append(inline(line))
        else:
            quote_lines.append(inline(line))
    quote_html = " ".join(quote_lines).strip()
    cite_html = " ".join(cite_lines).strip()
    parts = [f"<p>{quote_html}</p>"] if quote_html else []
    if cite_html:
        parts.append(f"<cite>{cite_html}</cite>")
    return f'<blockquote class="pullquote">{"".join(parts)}</blockquote>'


def render_body(body_src: str, order: list[str]) -> str:
    def ref_sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in order:
            order.append(key)
        n = order.index(key) + 1
        return (
            f'<sup class="fnref">'
            f'<a href="#" data-fn="{key}" aria-label="footnote {n}">{n}</a>'
            f"</sup>"
        )

    body_src = FN_REF.sub(ref_sub, body_src)

    # A line that contains nothing but an image markdown should be its own
    # block (figure) even if the user didn't surround it with blank lines.
    body_src = re.sub(
        r"(?m)^(\[?!\[[^\]\n]*\]\([^)\s]+\)\]?(?:\([^)\s]+\))?)[ \t]*$",
        r"\n\1\n",
        body_src,
    )

    # Extract fenced code blocks before splitting on blank lines.
    FENCE = re.compile(r"^```\s*\n(.*?)\n```\s*$", re.MULTILINE | re.DOTALL)
    fenced: list[str] = []

    FENCE_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)

    def _stash_fence(m: re.Match) -> str:
        content = m.group(1)
        content = FENCE_BOLD.sub(r"<strong>\1</strong>", content)
        fenced.append(f"<pre>{html.escape(content).replace('&lt;strong&gt;', '<strong>').replace('&lt;/strong&gt;', '</strong>')}</pre>")
        return f"\n\n__FENCED_{len(fenced) - 1}__\n\n"

    body_src = FENCE.sub(_stash_fence, body_src)

    blocks: list[str] = []
    for raw in re.split(r"\n\s*\n", body_src):
        block = raw.strip()
        if not block:
            continue
        if block.startswith("__FENCED_") and block.endswith("__"):
            idx = int(block[9:-2])
            blocks.append(fenced[idx])
        elif block.startswith("### "):
            blocks.append(f"<h3>{inline(block[4:].strip())}</h3>")
        elif block.startswith("## "):
            blocks.append(f"<h2>{inline(block[3:].strip())}</h2>")
        elif block.startswith("# "):
            blocks.append(f"<h1>{inline(block[2:].strip())}</h1>")
        elif block == "---":
            blocks.append('<p class="section-break">§</p>')
        elif block.startswith(">"):
            blocks.append(render_blockquote(block))
        elif (m := LINKED_IMAGE.fullmatch(block.strip())):
            alt, img_src, href = m.group(1), m.group(2), m.group(3)
            cap = f"<figcaption>{inline(alt)}</figcaption>" if alt else ""
            blocks.append(
                f'<figure><a href="{html.escape(href)}">'
                f'<img src="{img_src}" alt="{html.escape(alt)}">'
                f'</a>{cap}</figure>'
            )
        elif (m := IMAGE.fullmatch(block.strip())):
            alt, src = m.group(1), m.group(2)
            cap = f"<figcaption>{inline(alt)}</figcaption>" if alt else ""
            blocks.append(f'<figure><img src="{src}" alt="{html.escape(alt)}">{cap}</figure>')
        else:
            blocks.append(f"<p>{inline(block.replace('\n', ' '))}</p>")
    return "\n".join(blocks)


def first_heading(src: str) -> str:
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s.startswith("## "):
            return s[3:].strip()
    return "the llamas"


def validate(src: str, defs: dict[str, str]) -> list[str]:
    """Collect issues that would produce a broken document. Caller aborts."""
    issues: list[str] = []
    body = FN_DEF.sub("", src)
    refs = [m.group(1) for m in FN_REF.finditer(body)]
    seen: set[str] = set()
    for key in refs:
        if key in seen or key in defs:
            seen.add(key)
            continue
        seen.add(key)
        near = re.search(rf"^\[\^{re.escape(key)}\][ \t]+\S", src, re.MULTILINE)
        if near:
            issues.append(
                f"[^{key}] is referenced but its definition line is missing ':' — "
                f"change '[^{key}] ...' to '[^{key}]: ...'"
            )
        else:
            issues.append(f"[^{key}] is referenced but has no definition")
    return issues


META_HINT = re.compile(r"^<!--\s*([\w-]+)\s*:\s*(.+?)\s*-->\s*$", re.MULTILINE)


INDEX_LINK = re.compile(r"^\s*-\s*\[[^\]]+\]\(([^)]+)\.html\)", re.MULTILINE)
FOOTER_LINK = re.compile(r"<!--\s*footer-link:\s*(\S+)\s*-->")


VERSION_HINT = re.compile(r"<!--\s*version:\s*(v[\d.]+)")


def page_order() -> tuple[list[str], str | None, str]:
    """Derive sub-page sequence, footer stem, and version from index.md."""
    index_src = (MD_DIR / "index.md").read_text(encoding="utf-8")
    linked = [m.group(1) for m in INDEX_LINK.finditer(index_src)]
    footer_stem = None
    footer = FOOTER_LINK.search(index_src)
    if footer:
        footer_stem = footer.group(1).replace(".html", "")
        if footer_stem not in linked:
            linked.append(footer_stem)
    ver = VERSION_HINT.search(index_src)
    version = ver.group(1) if ver else "v0.0"
    return linked, footer_stem, version


def word_count() -> int:
    """Count words across all essay .md files (excluding index)."""
    total = 0
    for p in MD_DIR.glob("*.md"):
        if p.name == "index.md":
            continue
        text = p.read_text(encoding="utf-8")
        text = FN_DEF.sub("", text)
        text = META_HINT.sub("", text)
        text = re.sub(r"(?m)^#+\s*", "", text)
        text = re.sub(r"\[\^[\w-]+\]", "", text)
        text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        total += len(text.split())
    return total


def build(md_path: Path, order: list[str],
          footer_stem: str | None, version: str) -> Path | None:
    src = md_path.read_text(encoding="utf-8")
    src = src.replace("\r\n", "\n").replace("\f", "")

    meta: dict[str, str] = {}
    for m in META_HINT.finditer(src):
        meta[m.group(1)] = m.group(2).strip()
    src = META_HINT.sub("", src).lstrip()

    colors = {
        "bg": meta.get("bg", "#9bd4d6"),
        "text": meta.get("text", "#2b1810"),
    }

    defs = {m.group(1): m.group(2).strip() for m in FN_DEF.finditer(src)}

    issues = validate(src, defs)
    if issues:
        print(f"  {md_path.name}: not built — {len(issues)} issue(s):", file=sys.stderr)
        for msg in issues:
            print(f"    • {msg}", file=sys.stderr)
        return None

    body_src = FN_DEF.sub("", src).strip()

    def sub_times(m: re.Match) -> str:
        return times_in(body_src, m.group(1))

    body_src = TIMES.sub(sub_times, body_src)
    defs = {k: TIMES.sub(sub_times, v) for k, v in defs.items()}

    chart_html = starters_chart(body_src)
    body_src = STARTERS.sub(lambda _m: chart_html, body_src)
    defs = {k: STARTERS.sub(lambda _m: chart_html, v) for k, v in defs.items()}

    fn_order: list[str] = []
    body_html = render_body(body_src, fn_order)

    fn_blocks = "\n".join(
        f'<template data-fn="{html.escape(k)}">{inline(defs[k])}</template>'
        for k in fn_order
        if k in defs
    )

    title = first_heading(src)
    stem = md_path.stem
    idx = order.index(stem) if stem in order else -1

    is_footer = stem == footer_stem
    prev_stem = order[idx - 1] if idx > 0 and not is_footer else None
    if prev_stem:
        prev_md = MD_DIR / f"{prev_stem}.md"
        prev_label = first_heading(prev_md.read_text(encoding="utf-8")) if prev_md.exists() else prev_stem
        back_html = (
            f'<span class="prim-line">&larr; <a href="{prev_stem}.html">{html.escape(prev_label, quote=False)}</a></span>'
            f'<span class="sub-line"><span class="ghost">&larr; </span><a href="index.html">llamas</a></span>'
        )
    else:
        back_html = '<span class="prim-line">&larr; <a href="index.html">llamas</a></span>'

    next_stem = order[idx + 1] if 0 <= idx < len(order) - 1 else None
    mail_to = meta.get("mail", "")
    is_not_a_blog = md_path.name == "not-a-blog.md"
    sub_blog = (
        '' if is_not_a_blog
        else '<span class="sub-line"><a href="not-a-blog.html">Not a blog</a><span class="ghost"> &rarr;</span></span>'
    )
    if mail_to:
        envelope_svg = (
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<rect x="3" y="5" width="18" height="14" rx="2" />'
            '<path d="M3 7l9 6 9-6" />'
            '</svg>'
        )
        next_html = (
            f'<nav class="next mail"><a href="mailto:{html.escape(mail_to)}" '
            f'aria-label="Email Colin">{envelope_svg}</a></nav>'
        )
    elif next_stem:
        next_md = MD_DIR / f"{next_stem}.md"
        next_label = first_heading(next_md.read_text(encoding="utf-8")) if next_md.exists() else next_stem
        next_html = (
            f'<nav class="next"><span class="prim-line">'
            f'<a href="{next_stem}.html">{html.escape(next_label, quote=False)}</a> &rarr;'
            f'</span>{sub_blog}</nav>'
        )
    elif sub_blog:
        next_html = f'<nav class="next">{sub_blog}</nav>'
    else:
        next_html = ""

    if is_footer and not version.startswith("v1."):
        wc = word_count()
        body_html += f'\n<p>{wc:,} words. {version}</p>'

    page = (
        TEMPLATE
        .replace("__TITLE__", html.escape(title))
        .replace("__BODY__", body_html)
        .replace("__FOOTNOTES__", fn_blocks)
        .replace("__BG__", colors["bg"])
        .replace("__TEXT__", colors["text"])
        .replace("__BACK__", back_html)
        .replace("__NEXT__", next_html)
    )

    out = LLAMA / md_path.with_suffix(".html").name
    out.write_text(page, encoding="utf-8")
    return out


LIST_ITEM = re.compile(r"^\s*[-*]\s+(.*)$", re.MULTILINE)


def build_index(md_path: Path) -> Path:
    src = md_path.read_text(encoding="utf-8")
    src = src.replace("\r\n", "\n").replace("\f", "")

    meta: dict[str, str] = {}
    for m in META_HINT.finditer(src):
        meta[m.group(1)] = m.group(2).strip()
    src = META_HINT.sub("", src).strip()

    headline_lines = [
        line[2:].strip()
        for line in src.splitlines()
        if line.strip().startswith("# ")
    ]
    if not headline_lines:
        headline_lines = [first_heading(src)]
    spans = "".join(f"<span>{html.escape(line)}</span>" for line in headline_lines)
    raw_headline = " ".join(headline_lines)

    items: list[str] = []
    for m in LIST_ITEM.finditer(src):
        item = m.group(1).strip()
        link = LINK.fullmatch(item)
        if link:
            text, href = link.group(1), link.group(2)
            items.append(f'    <a href="{html.escape(href)}">{html.escape(text, quote=False)}</a>')
        else:
            items.append(f'    <a href="#">{html.escape(item, quote=False)}</a>')

    page = (
        INDEX_TEMPLATE
        .replace("__PAGE_TITLE__", html.escape(meta.get("page-title", raw_headline)))
        .replace("__HEADLINE__", spans)
        .replace("__SENTENCES__", "\n".join(items))
        .replace("__FOOTER_LINK__", html.escape(meta.get("footer-link", "not-a-blog.html")))
        .replace("__FOOTER_LABEL__", html.escape(meta.get("footer-label", "Not a blog by Colin Summers")))
        .replace("__VERSION__", html.escape(meta.get("version", "")))
    )

    out = LLAMA / md_path.with_suffix(".html").name
    out.write_text(page, encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] if len(argv) > 1 else sorted(MD_DIR.glob("*.md"))
    if not targets:
        print("nothing to build", file=sys.stderr)
        return 1
    order, footer_stem, version = page_order()
    failed = 0
    for p in targets:
        if p.name == "index.md":
            out = build_index(p)
        else:
            out = build(p, order, footer_stem, version)
        if out is None:
            failed += 1
        else:
            print(f"built {out.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
