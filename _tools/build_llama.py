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
from pathlib import Path

from llama_shared import ABBREVS, sentence_starters, times_in

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
CAIBAL_WORD = re.compile(r"\bcaibal\b", re.IGNORECASE)


def _is_external(url: str) -> bool:
    return url.startswith("http") and "mightycheese.com" not in url


def _target(url: str) -> str:
    return ' target="_blank"' if _is_external(url) else ""


def _autolink_repl(m: re.Match) -> str:
    url = m.group(1)
    trail = ""
    while url and url[-1] in ".,;:!?)":
        trail = url[-1] + trail
        url = url[:-1]
    return f'<a href="{url}"{_target(url)}>{url}</a>{trail}'


def _link_repl(m: re.Match) -> str:
    text, url = m.group(1), m.group(2)
    return f'<a href="{url}"{_target(url)}>{text}</a>'


def inline(text: str) -> str:
    text = LINK.sub(_link_repl, text)
    text = URL_AUTOLINK.sub(_autolink_repl, text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = ITALIC.sub(r"<em>\1</em>", text)
    return text


def autolink_caibal(body_src: str, stem: str) -> str:
    """Link first bare 'caibal' on non-caibal pages to caibal.html."""
    if stem == "caibal":
        return body_src
    return CAIBAL_WORD.sub(r"[\g<0>](caibal.html)", body_src, count=1)


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


def render_body(body_src: str) -> tuple[str, list[str]]:
    fn_order: list[str] = []
    fn_index: dict[str, int] = {}

    def ref_sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in fn_index:
            fn_index[key] = len(fn_order) + 1
            fn_order.append(key)
        n = fn_index[key]
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
        raw = m.group(1)
        parts = FENCE_BOLD.split(raw)
        # parts alternates: text, bold_content, text, bold_content, ...
        out = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                out.append(html.escape(part))
            else:
                out.append(f"<strong>{html.escape(part)}</strong>")
        fenced.append(f"<pre>{''.join(out)}</pre>")
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
                f'<figure><a href="{html.escape(href)}"{_target(href)}>'
                f'<img src="{img_src}" alt="{html.escape(alt)}">'
                f'</a>{cap}</figure>'
            )
        elif (m := IMAGE.fullmatch(block.strip())):
            alt, src = m.group(1), m.group(2)
            cap = f"<figcaption>{inline(alt)}</figcaption>" if alt else ""
            blocks.append(f'<figure><img src="{src}" alt="{html.escape(alt)}">{cap}</figure>')
        elif all(re.match(r"^\s*[-*]\s+", line) for line in block.splitlines() if line.strip()):
            items = []
            for line in block.splitlines():
                stripped = line.strip()
                if stripped:
                    text = re.sub(r"^[-*]\s+", "", stripped)
                    items.append(f"<li>{inline(text)}</li>")
            blocks.append("<ul>\n" + "\n".join(items) + "\n</ul>")
        else:
            blocks.append(f"<p>{inline(block.replace('\n', ' '))}</p>")
    return "\n".join(blocks), fn_order


def first_heading(src: str) -> str:
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s.startswith("## "):
            return s[3:].strip()
    return "the llamas"


def fix_endnotes(md_path: Path, src: str) -> str:
    """Reorder endnote definitions to match first-reference order in the body.
    Warns about orphaned definitions (defined but never referenced).
    Writes back to the source file only if something changed."""
    body = FN_DEF.sub("", src)
    ref_order: list[str] = []
    for m in FN_REF.finditer(body):
        key = m.group(1)
        if key not in ref_order:
            ref_order.append(key)

    defs: dict[str, str] = {}
    for m in FN_DEF.finditer(src):
        defs[m.group(1)] = m.group(0)

    if not defs:
        return src

    orphans = [k for k in defs if k not in ref_order]
    for k in orphans:
        print(f"  {md_path.name}: [^{k}] is defined but never referenced — may belong in another file", file=sys.stderr)

    ordered_keys = [k for k in ref_order if k in defs] + orphans
    old_keys = list(defs.keys())
    if ordered_keys == old_keys:
        return src

    stripped = FN_DEF.sub("", src).rstrip()
    new_defs = "\n\n".join(defs[k] for k in ordered_keys)
    new_src = stripped + "\n\n" + new_defs + "\n"

    md_path.write_text(new_src, encoding="utf-8")
    moved = [k for k, o in zip(ordered_keys, old_keys) if k != o]
    print(f"  {md_path.name}: reordered endnotes ({', '.join(moved)})", file=sys.stderr)
    return new_src


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
INDEX_ITEM = re.compile(r"^\s*-\s*\[([^\]]+)\]\(([^)]+)\)", re.MULTILINE)
FOOTER_LINK = re.compile(r"<!--\s*footer-link:\s*(\S+)\s*-->")
FOOTER_LABEL = re.compile(r"<!--\s*footer-label:\s*(.+?)\s*-->")
INDEX_HEADING = re.compile(r"^##?\s+(.+)$", re.MULTILINE)


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


def sidebar_items() -> tuple[str, list[tuple[str, str]], str, str]:
    """Return (title, [(href, text), ...], footer_href, footer_label) from index.md."""
    index_src = (MD_DIR / "index.md").read_text(encoding="utf-8")
    headings = [m.group(1).strip() for m in INDEX_HEADING.finditer(index_src)]
    title = " ".join(headings)
    items = [(m.group(2), m.group(1)) for m in INDEX_ITEM.finditer(index_src)]
    fl = FOOTER_LINK.search(index_src)
    footer_href = fl.group(1) if fl else "not-a-blog.html"
    flab = FOOTER_LABEL.search(index_src)
    footer_label = flab.group(1) if flab else "Not a blog by Colin Summers"
    footer_parts = footer_label.split(" by ", 1)
    return title, items, footer_href, footer_parts


def build_sidebar(stem: str) -> str:
    """Build the sidebar nav HTML for a given page stem."""
    title, items, footer_href, footer_parts = sidebar_items()
    parts: list[str] = []
    for href, text in items:
        page_stem = href.replace(".html", "")
        if page_stem == stem:
            parts.append(f'<span class="current">{html.escape(text, quote=False)}</span>')
        else:
            parts.append(f'<a href="{html.escape(href)}">{html.escape(text, quote=False)}</a>')
    sentences = " ".join(parts)
    link_label = footer_parts[0] if footer_parts else "Not a blog"
    byline = f"by {footer_parts[1]}" if len(footer_parts) > 1 else ""
    lines = [
        '<nav class="sidebar">',
        f'  <a class="title" href="index.html">{html.escape(title)}</a>',
        f'  {sentences}',
        f'  <a class="notablog" href="{html.escape(footer_href)}">{html.escape(link_label)}</a>',
    ]
    if byline:
        lines.append(f'  <span class="byline">{html.escape(byline)}</span>')
    lines.append('</nav>')
    return "\n".join(lines)


def _count_words(p: Path) -> int:
    text = p.read_text(encoding="utf-8")
    text = FN_DEF.sub("", text)
    text = META_HINT.sub("", text)
    text = re.sub(r"(?m)^#+\s*", "", text)
    text = re.sub(r"\[\^[\w-]+\]", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return len(text.split())


def word_count() -> int:
    """Count words across all essay .md files (excluding index)."""
    return sum(
        _count_words(p)
        for p in MD_DIR.glob("*.md")
        if p.name != "index.md"
    )


def per_file_word_counts(order: list[str]) -> list[tuple[str, str, int]]:
    """Return (stem, title, count) for each essay in index order."""
    results = []
    for stem in order:
        p = MD_DIR / f"{stem}.md"
        if not p.exists():
            continue
        title = first_heading(p.read_text(encoding="utf-8"))
        results.append((stem, title, _count_words(p)))
    return results


def build(md_path: Path, order: list[str],
          footer_stem: str | None, version: str) -> Path | None:
    src = md_path.read_text(encoding="utf-8")
    src = src.replace("\r\n", "\n").replace("\f", "")
    src = fix_endnotes(md_path, src)

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

    body_src = autolink_caibal(body_src, md_path.stem)

    body_html, fn_order = render_body(body_src)

    fn_blocks = "\n".join(
        f'<template data-fn="{html.escape(k)}">{inline(defs[k])}</template>'
        for k in fn_order
        if k in defs
    )

    title = first_heading(src)
    stem = md_path.stem
    idx = order.index(stem) if stem in order else -1

    is_footer = stem == footer_stem

    if is_footer:
        mail_to = meta.get("mail", "")
        envelope_svg = (
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<rect x="3" y="5" width="18" height="14" rx="2" />'
            '<path d="M3 7l9 6 9-6" />'
            '</svg>'
        )
        pdf_svg = (
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M6 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6H6z" />'
            '<path d="M14 2v6h6" />'
            '<text x="12" y="17" text-anchor="middle" '
            'font-family="Helvetica,Arial,sans-serif" font-size="6" font-weight="700" '
            'fill="currentColor" stroke="none">PDF</text>'
            '</svg>'
        )
        sidebar_html = (
            '<nav class="sidebar">'
            '<span class="prim-line">&larr; <a href="index.html">llamas</a></span>'
        )
        if mail_to:
            sidebar_html += (
                f'<a href="mailto:{html.escape(mail_to)}" title="Email me">{envelope_svg}</a>'
                f'<a href="llama-essays.pdf" title="Entire set as PDF" download>{pdf_svg}</a>'
            )
        sidebar_html += '</nav>'
        bottom_nav = ''
    else:
        sidebar_html = build_sidebar(stem)
        _, items, _, _ = sidebar_items()
        item_stems = [href.replace(".html", "") for href, _ in items]
        si = item_stems.index(stem) if stem in item_stems else -1
        if 0 <= si < len(items) - 1:
            next_href, next_text = items[si + 1]
            bottom_nav = (
                f'<p class="bottom-nav">'
                f'<a href="{html.escape(next_href)}">{html.escape(next_text, quote=False)} &rarr;</a>'
                f'</p>'
            )
        else:
            bottom_nav = ''

    if is_footer:
        wc = word_count()
        file_counts = per_file_word_counts(order)
        rows = "".join(
            f'<span class="fc-n">{count:,}</span>'
            f'<span class="fc-t">{html.escape(title, quote=False)}</span>'
            for _, title, count in file_counts
        )
        body_html += (
            f'\n<p class="dev-wc" hidden>{wc:,} words. {version}'
            f'<span class="file-counts">{rows}</span></p>'
        )

    page = (
        TEMPLATE
        .replace("__TITLE__", html.escape(title))
        .replace("__BODY__", body_html)
        .replace("__FOOTNOTES__", fn_blocks)
        .replace("__BG__", colors["bg"])
        .replace("__TEXT__", colors["text"])
        .replace("__SIDEBAR__", sidebar_html)
        .replace("__BOTTOMNAV__", bottom_nav)
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

    headline_lines = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("## "):
            headline_lines.append(s[3:].strip())
        elif s.startswith("# "):
            headline_lines.append(s[2:].strip())
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


def build_proof(order: list[str]) -> Path | None:
    """Spell-check all essay markdown files, write findings to proof.md."""
    from datetime import date
    try:
        from spellchecker import SpellChecker
    except ImportError:
        print("  skipping proof (pyspellchecker not installed)", file=sys.stderr)
        return None

    spell = SpellChecker()
    words_file = TOOLS / "proof_known_words.txt"
    if words_file.exists():
        known = [w.strip() for w in words_file.read_text().splitlines() if w.strip()]
        spell.word_frequency.load_words(known)
    # Airport/station codes — all caps, 3–4 chars
    ICAO_RE = re.compile(r"^[A-Z]{3,4}$")

    STRIP_MD = re.compile(r"""
        \[\^[\w-]+\]:.*$          |  # footnote defs
        \[\^[\w-]+\]              |  # footnote refs
        !\[[^\]]*\]\([^)]+\)      |  # images
        \[[^\]]*\]\([^)]+\)       |  # links (keep text via later sub)
        <!--.*?-->                |  # HTML comments
        \{\{[^}]+\}\}            |  # template tags
        ^#+\s+                    |  # headings
        ^\s*>\s*                  |  # blockquote markers
        [*_`~]                       # inline formatting
    """, re.MULTILINE | re.VERBOSE)
    LINK_TEXT = re.compile(r"\[([^\]]+)\]\([^)]+\)")
    DOUBLE_WORD = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)
    CONTRACTION_RE = re.compile(r"\w+'(s|t|ll|ve|re|d|m|nt)\b", re.IGNORECASE)
    WORD_RE = re.compile(r"[a-zA-Z]+")

    out_lines = ["# Llama Essays — Proof", f"Generated {date.today()}", ""]
    has_findings = False

    for stem in order:
        p = MD_DIR / f"{stem}.md"
        if not p.exists():
            continue
        raw = p.read_text(encoding="utf-8")
        lines = raw.splitlines()
        findings: list[str] = []

        for lineno, line in enumerate(lines, 1):
            clean = LINK_TEXT.sub(r"\1", line)
            clean = STRIP_MD.sub("", clean)
            clean = re.sub(r"&\w+;", "", clean)  # HTML entities
            clean = re.sub("[‘’‚ʼ`´]", "'", clean)
            clean = CONTRACTION_RE.sub("", clean)

            words = [w for w in WORD_RE.findall(clean) if len(w) > 2]
            words_to_check = [w for w in words if not ICAO_RE.match(w)]
            misspelled = spell.unknown(words_to_check)
            for word in misspelled:
                findings.append(
                    f"- **Line {lineno}** — `{word}` — Possible misspelling"
                )

            m = DOUBLE_WORD.search(clean)
            if m and m.group(1).lower() not in {"that", "had", "the"}:
                findings.append(
                    f"- **Line {lineno}** — `{m.group(0)}` — Repeated word"
                )

        if findings:
            has_findings = True
            out_lines.append(f"## {stem}.md")
            out_lines.append("")
            out_lines.extend(findings)
            out_lines.append("")

    proof_path = LLAMA / "proof.md"
    if not has_findings:
        if proof_path.exists():
            proof_path.unlink()
        return None
    proof_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return proof_path


def main(argv: list[str]) -> int:
    full_build = len(argv) <= 1
    targets = [Path(a) for a in argv[1:]] if not full_build else sorted(MD_DIR.glob("*.md"))
    if not targets:
        print("nothing to build", file=sys.stderr)
        return 1
    order, footer_stem, version = page_order()

    if full_build:
        first_mention = None
        def_file = None
        for stem in order:
            if stem == "caibal":
                continue
            p = MD_DIR / f"{stem}.md"
            if not p.exists():
                continue
            src = p.read_text(encoding="utf-8")
            body = FN_DEF.sub("", src)
            if first_mention is None and CAIBAL_WORD.search(body):
                first_mention = stem
            if any(m.group(1) == "cailbal" for m in FN_DEF.finditer(src)):
                def_file = stem
        if def_file and first_mention and def_file != first_mention:
            print(
                f"  warning: [^cailbal] endnote is in {def_file}.md "
                f"but first 'caibal' mention is in {first_mention}.md",
                file=sys.stderr,
            )

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
    if full_build and not failed:
        from build_llama_pdf import essay_order, render_pdf
        pdf_out = ROOT / "llama" / "llama-essays.pdf"
        render_pdf(essay_order(), pdf_out)
        proof_out = build_proof(order)
        if proof_out:
            print(f"proof written to {proof_out.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
