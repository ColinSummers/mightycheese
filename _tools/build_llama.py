#!/usr/bin/env python3
"""Build llama/*.html sub-pages from llama/*.md (except index.md).

Run after editing any markdown in llama/. The index page is hand-maintained.

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
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LLAMA = ROOT / "llama"

FN_DEF = re.compile(r"^\[\^([\w-]+)\]:[ \t]*(.*)$", re.MULTILINE)
FN_REF = re.compile(r"\[\^([\w-]+)\]")
ITALIC = re.compile(r"\*([^*\n]+)\*")


def inline(text: str) -> str:
    return ITALIC.sub(r"<em>\1</em>", text)


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

    blocks: list[str] = []
    for raw in re.split(r"\n\s*\n", body_src):
        block = raw.strip()
        if not block:
            continue
        if block.startswith("## "):
            blocks.append(f"<h2>{inline(block[3:].strip())}</h2>")
        elif block.startswith("# "):
            blocks.append(f"<h1>{inline(block[2:].strip())}</h1>")
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
    background: #9bd4d6;
    color: #2b1810;
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
  nav.back a {
    color: inherit;
    text-decoration: none;
    border-bottom: 1px solid currentColor;
  }
  @media (max-width: 720px) {
    nav.back {
      position: static;
      max-width: 38em;
      margin: 0 auto 2em;
    }
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
  sup.fnref {
    font-size: 0.65em;
    line-height: 0;
    margin-left: 0.05em;
  }
  sup.fnref a {
    color: inherit;
    text-decoration: none;
    border-bottom: 1px solid currentColor;
    padding: 0 0.2em;
  }
  sup.fnref a:hover { background: rgba(43,24,16,0.08); }
  #fnpop {
    position: absolute;
    max-width: 360px;
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
</style>
</head>
<body>
<nav class="back"><a href="index.html">&larr; llamas</a></nav>
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


def build(md_path: Path) -> Path:
    src = md_path.read_text(encoding="utf-8")
    src = src.replace("\r\n", "\n").replace("\f", "")
    defs = {m.group(1): m.group(2).strip() for m in FN_DEF.finditer(src)}
    body_src = FN_DEF.sub("", src).strip()

    order: list[str] = []
    body_html = render_body(body_src, order)

    fn_blocks = "\n".join(
        f'<template data-fn="{html.escape(k)}">{inline(defs[k])}</template>'
        for k in order
        if k in defs
    )

    title = first_heading(src)
    page = (
        TEMPLATE
        .replace("__TITLE__", html.escape(title))
        .replace("__BODY__", body_html)
        .replace("__FOOTNOTES__", fn_blocks)
    )

    out = md_path.with_suffix(".html")
    out.write_text(page, encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] if len(argv) > 1 else sorted(
        p for p in LLAMA.glob("*.md") if p.name != "index.md"
    )
    if not targets:
        print("nothing to build", file=sys.stderr)
        return 1
    for p in targets:
        out = build(p)
        print(f"built {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
