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

ROOT = Path(__file__).resolve().parent.parent
LLAMA = ROOT / "llama"
MD_DIR = LLAMA / "markdown"

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

    blocks: list[str] = []
    for raw in re.split(r"\n\s*\n", body_src):
        block = raw.strip()
        if not block:
            continue
        if block.startswith("## "):
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
            blocks.append(f"<p>{inline(block.replace(chr(10), ' '))}</p>")
    return "\n".join(blocks)


def first_heading(src: str) -> str:
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s.startswith("## "):
            return s[3:].strip()
    return "the llamas"


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mighty Cheese | __TITLE__</title>
<link href="https://fonts.googleapis.com/css2?family=Charmonman:wght@400;700&family=Quicksand:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  html, body {
    margin: 0;
    padding: 0;
    background: __BG__;
    color: __TEXT__;
    font-family: 'Quicksand', 'Avenir Next', 'Avenir', system-ui, sans-serif;
  }
  body {
    padding: 6vh 8.4vw;
    box-sizing: border-box;
  }
  nav.back {
    position: fixed;
    top: 6vh;
    left: 8.4vw;
    font-size: 0.95rem;
  }
  nav.next {
    position: fixed;
    bottom: 6vh;
    right: 8.4vw;
    font-size: 0.95rem;
  }
  nav.back a, nav.next a {
    color: inherit;
    text-decoration: none;
  }
  nav.back > a, nav.next > a, nav.back .sub-line, nav.next .sub-line,
  nav.back .prim-line, nav.next .prim-line {
    display: block;
  }
  nav.back a:hover, nav.next a:hover {
    text-decoration: underline;
  }
  nav.back .sub-line, nav.next .sub-line {
    font-size: 0.85em;
    opacity: 0.7;
    margin-top: 0.25em;
  }
  nav.back .sub-line .ghost, nav.next .sub-line .ghost {
    color: __BG__;
    font-size: 1.18em;
  }
  nav.next { text-align: right; }
  nav.next.mail a {
    display: inline-flex;
    align-items: center;
  }
  nav.next.mail svg {
    width: 2.4rem;
    height: 2.4rem;
    stroke: currentColor;
    fill: none;
    stroke-width: 1.5;
    opacity: 0.85;
    transition: opacity 0.2s ease;
  }
  nav.next.mail a:hover svg { opacity: 1; }
  @media (max-width: 720px) {
    nav.back, nav.next {
      position: static;
      max-width: 38em;
      margin: 0 auto 2em;
    }
    nav.next { text-align: right; }
  }
  main {
    max-width: 38em;
    margin: 0 auto;
  }
  h1, h2 {
    font-family: 'Charmonman', 'Quicksand', cursive;
    font-weight: 700;
    line-height: 1.1;
    margin: 0 0 0.7em 0;
  }
  h1 { font-size: clamp(3rem, 8vw, 6.2rem); }
  h2 { font-size: clamp(2.5rem, 6.4vw, 4.6rem); }
  p {
    font-size: clamp(1.2rem, 1.8vw, 1.55rem);
    line-height: 1.55;
    margin: 0 0 1.1em 0;
  }
  em { font-style: italic; }
  strong { font-weight: 600; }
  main p a {
    color: inherit;
    text-decoration: underline;
    text-decoration-thickness: 1px;
    text-underline-offset: 0.18em;
  }
  main p a:hover { background: rgba(43,24,16,0.08); }
  figure {
    margin: 2.4em 0;
    text-align: center;
  }
  figure img {
    max-width: 100%;
    height: auto;
    border-radius: 6px;
    box-shadow: 0 6px 22px rgba(43,24,16,0.25);
  }
  figure figcaption {
    margin-top: 0.7em;
    font-size: 0.9rem;
    line-height: 1.4;
    opacity: 0.75;
    font-style: italic;
  }
  p.section-break {
    text-align: center;
    font-family: 'Charmonman', 'Quicksand', cursive;
    font-weight: 700;
    font-size: clamp(1.9rem, 3.4vw, 2.8rem);
    line-height: 1.25;
    margin: 1.35em 0;
  }
  blockquote.pullquote {
    margin: 2.2em -0.5em;
    padding: 1.1em 0.5em 1.2em;
    border-top: 1px solid currentColor;
    border-bottom: 1px solid currentColor;
    text-align: center;
    font-family: 'Charmonman', 'Quicksand', cursive;
    font-size: clamp(1.9rem, 3.4vw, 2.8rem);
    line-height: 1.25;
  }
  blockquote.pullquote p {
    margin: 0;
    font-size: inherit;
    line-height: inherit;
  }
  blockquote.pullquote strong { font-weight: inherit; }
  blockquote.pullquote cite {
    display: block;
    font-family: 'Quicksand', sans-serif;
    font-style: normal;
    font-weight: 500;
    font-size: 0.85rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    opacity: 0.7;
    margin-top: 0.9em;
  }
  sup.fnref {
    font-size: 0.65em;
    line-height: 0;
    margin-left: 0.05em;
  }
  sup.fnref a {
    color: #b04a2a;
    text-decoration: none;
    font-weight: 700;
    padding: 0 0.15em;
  }
  sup.fnref a:hover { background: rgba(176, 74, 42, 0.14); }
  #fnpop {
    position: absolute;
    width: 320px;
    max-height: 80vh;
    overflow-y: auto;
    background: #f5e6c5;
    color: #2b1810;
    padding: 1em 1.15em;
    border-radius: 6px;
    box-shadow: 0 8px 28px rgba(43,24,16,0.28);
    font-size: 0.95rem;
    line-height: 1.5;
    z-index: 10;
  }
  #fnpop[hidden] { display: none; }
  #fnpop a {
    color: #8a3324;
    text-decoration: none;
  }
  #fnpop a:hover {
    text-decoration: underline;
    text-decoration-thickness: 1px;
    text-underline-offset: 0.15em;
  }
  .starter-chart { font-size: 0.85rem; line-height: 1.35; }
  .starter-pie { display: block; margin: 0 auto 0.9em; }
  .starter-legend {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .starter-legend li {
    display: flex;
    align-items: center;
    gap: 0.55em;
    padding: 0.12em 0;
  }
  .starter-legend .sw {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    flex-shrink: 0;
  }
  .starter-legend .lab { flex: 1; font-weight: 500; }
  .starter-legend .num {
    font-family: 'SF Mono', Menlo, Consolas, ui-monospace, monospace;
    font-size: 0.85em;
    font-variant-numeric: tabular-nums;
    opacity: 0.75;
  }
  .starter-meta {
    margin-top: 0.7em;
    text-align: center;
    font-family: 'SF Mono', Menlo, Consolas, ui-monospace, monospace;
    font-size: 0.78em;
    opacity: 0.7;
  }
</style>
</head>
<body>
<nav class="back">__BACK__</nav>
__NEXT__
<main>
__BODY__
</main>
__FOOTNOTES__
<script>
  const popup = document.createElement('div');
  popup.id = 'fnpop';
  popup.hidden = true;
  document.body.appendChild(popup);

  document.addEventListener('click', (e) => {
    const ref = e.target.closest('.fnref a');
    if (ref) {
      e.preventDefault();
      const key = ref.dataset.fn;
      const tpl = document.querySelector('template[data-fn="' + key + '"]');
      if (!tpl) return;
      popup.innerHTML = tpl.innerHTML;
      popup.hidden = false;
      const rect = ref.getBoundingClientRect();
      const popRect = popup.getBoundingClientRect();
      let left = rect.left + window.scrollX;
      if (left + popRect.width > window.innerWidth + window.scrollX - 20) {
        left = window.innerWidth + window.scrollX - popRect.width - 20;
      }
      popup.style.left = left + 'px';
      popup.style.top = (rect.bottom + window.scrollY + 8) + 'px';
      return;
    }
    if (!e.target.closest('#fnpop')) popup.hidden = true;
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') popup.hidden = true;
  });
</script>
</body>
</html>
"""


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


def prev_map() -> dict[str, Path]:
    """Build {next-target.html: source-md-path} from all .md files in MD_DIR."""
    m: dict[str, Path] = {}
    for p in MD_DIR.glob("*.md"):
        if p.name == "index.md":
            continue
        text = p.read_text(encoding="utf-8")
        for hint in META_HINT.finditer(text):
            if hint.group(1) == "next":
                m[hint.group(2).strip()] = p
    return m


def build(md_path: Path) -> Path | None:
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

    order: list[str] = []
    body_html = render_body(body_src, order)

    fn_blocks = "\n".join(
        f'<template data-fn="{html.escape(k)}">{inline(defs[k])}</template>'
        for k in order
        if k in defs
    )

    title = first_heading(src)
    out_name = md_path.with_suffix(".html").name
    prev_src = prev_map().get(out_name)
    if prev_src:
        prev_label = first_heading(prev_src.read_text(encoding="utf-8"))
        prev_href = prev_src.with_suffix(".html").name
        back_html = (
            f'<span class="prim-line">&larr; <a href="{html.escape(prev_href)}">{html.escape(prev_label, quote=False)}</a></span>'
            f'<span class="sub-line"><span class="ghost">&larr; </span><a href="index.html">llamas</a></span>'
        )
    else:
        back_html = '<span class="prim-line">&larr; <a href="index.html">llamas</a></span>'

    next_href = meta.get("next", "")
    next_label = meta.get("next-label", "")
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
    elif next_href:
        if not next_label:
            next_md = MD_DIR / Path(next_href).with_suffix(".md").name
            next_label = first_heading(next_md.read_text(encoding="utf-8")) if next_md.exists() else next_href
        next_html = (
            f'<nav class="next"><span class="prim-line">'
            f'<a href="{html.escape(next_href)}">{html.escape(next_label, quote=False)}</a> &rarr;'
            f'</span>{sub_blog}</nav>'
        )
    elif sub_blog:
        next_html = f'<nav class="next">{sub_blog}</nav>'
    else:
        next_html = ""

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


INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mighty Cheese | __PAGE_TITLE__</title>
<link href="https://fonts.googleapis.com/css2?family=Charmonman:wght@400;700&family=Quicksand:wght@400;500;600&family=Storyscript&display=swap" rel="stylesheet">
<style>
  html, body {
    margin: 0;
    padding: 0;
    height: 100%;
    background: #2b1810;
    color: #9bd4d6;
    font-family: 'Quicksand', 'Avenir Next', 'Avenir', system-ui, sans-serif;
  }
  body {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 6vh 8.4vw 14vh;
    box-sizing: border-box;
  }
  main {
    width: 100%;
    max-width: 1400px;
    margin: auto;
  }
  h1 {
    font-family: 'Charmonman', 'Quicksand', cursive;
    font-weight: 700;
    font-size: clamp(2.2rem, 6.4vw, 7rem);
    line-height: 1.05;
    margin: 0 0 0.6em 0;
    letter-spacing: 0;
  }
  h1 span {
    display: block;
    white-space: nowrap;
  }
  p {
    font-family: 'Storyscript', 'Quicksand', cursive;
    font-weight: 400;
    font-size: clamp(1.95rem, 3.9vw, 5.4rem);
    line-height: 1.3;
    margin: 0 12.5%;
  }
  @media (max-width: 1100px) {
    body { justify-content: flex-start; }
    p { margin: 0; }
  }
  p a {
    color: inherit;
    text-decoration: none;
    opacity: 0.18;
    transition: opacity 0.55s ease, text-shadow 0.55s ease;
  }
  p a.lit {
    opacity: 1;
    text-shadow: 0 0 18px rgba(155, 212, 214, 0.35);
  }
  p a:hover {
    text-decoration: underline;
    text-decoration-thickness: 2px;
    text-underline-offset: 0.08em;
  }
  .bottomright {
    position: absolute;
    right: 6vw;
    bottom: 3vh;
    text-align: right;
    color: #b04a2a;
  }
  a.notablog {
    color: inherit;
    font-family: 'Storyscript', 'Quicksand', cursive;
    font-size: clamp(0.765rem, 1.98vw, 1.89rem);
    text-decoration: none;
    opacity: 0.85;
  }
  a.notablog:hover { opacity: 1; text-decoration: underline; }
  .version {
    margin-top: 0.2em;
    font-family: 'Quicksand', sans-serif;
    font-size: clamp(0.38rem, 0.99vw, 0.945rem);
    opacity: 0.7;
    letter-spacing: 0.05em;
  }
</style>
</head>
<body>
<main>
  <h1>__HEADLINE__</h1>
  <p>
__SENTENCES__
  </p>
</main>
<div class="bottomright">
  <a class="notablog" href="__FOOTER_LINK__">__FOOTER_LABEL__</a>
  <div class="version">__VERSION__</div>
</div>
<script>
  window.addEventListener('load', () => {
    const links = document.querySelectorAll('p a');
    links.forEach((a, i) => setTimeout(() => a.classList.add('lit'), 400 + i * 1100));
  });
</script>
</body>
</html>
"""


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
    failed = 0
    for p in targets:
        if p.name == "index.md":
            out = build_index(p)
        else:
            out = build(p)
        if out is None:
            failed += 1
        else:
            print(f"built {out.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
