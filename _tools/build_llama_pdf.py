#!/usr/bin/env python3
"""Build PDF(s) of llama essays.

Usage:
    python3 build_llama_pdf.py                # all essays, ordered by index
    python3 build_llama_pdf.py history.md      # single essay

Uses pandoc (markdown→HTML with footnotes) and weasyprint (HTML→PDF).
Resolves {{times:}} and {{starters:}} template placeholders from the
markdown sources, strips images, and renders endnotes per essay.
"""

import re
import subprocess
import sys
from pathlib import Path

from llama_shared import ABBREVS, sentence_starters, times_in

MD_DIR = Path(__file__).resolve().parent.parent / "llama" / "markdown"
DESKTOP = Path.home() / "Desktop"

LINK_RE = re.compile(r"^\s*-\s*\[[^\]]+\]\(([^)]+)\.html\)", re.MULTILINE)
FOOTER_RE = re.compile(r"<!--\s*footer-link:\s*(\S+\.html)\s*-->")


def essay_order() -> list[str]:
    """Read link order from index.md: index first, then linked essays,
    then the footer-link page, then any remaining .md files."""
    index = MD_DIR / "index.md"
    src = index.read_text(encoding="utf-8")
    linked = [m.group(1) + ".md" for m in LINK_RE.finditer(src)]
    footer = FOOTER_RE.search(src)
    if footer:
        linked.append(footer.group(1).replace(".html", ".md"))
    order = ["index.md"] + linked
    seen = set(order)
    for p in sorted(MD_DIR.glob("*.md")):
        if p.name not in seen:
            order.append(p.name)
    return order

TIMES_RE = re.compile(r"\{\{times:\s*([^}]+?)\s*\}\}")
STARTERS_RE = re.compile(r"\{\{starters:\s*top10\s*\}\}")
IMAGE_RE = re.compile(r"!?\[!\[[^\]]*\]\([^)]+\)\]\([^)]+\)|!\[[^\]\n]*\]\([^)]+\)")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def starters_text(body: str) -> str:
    counts = sentence_starters(body)
    total = sum(counts.values()) or 1
    top10 = counts.most_common(10)
    lines = ["*Top 10 sentence starters in this essay:*", ""]
    for word, count in top10:
        pct = count * 100 / total
        lines.append(f"- **{word}**: {count} ({pct:.1f}%)")
    rest = total - sum(n for _, n in top10)
    if rest > 0:
        lines.append(f"- *Other*: {rest} ({rest * 100 / total:.1f}%)")
    lines.append(f"\n*{total} sentences, {len(counts)} unique starters*")
    return "\n".join(lines)


def process_md(path: Path) -> str:
    original = path.read_text(encoding="utf-8")
    text = IMAGE_RE.sub("", original)
    text = COMMENT_RE.sub("", text)

    def replace_times(m):
        return times_in(original, m.group(1))
    text = TIMES_RE.sub(replace_times, text)
    text = STARTERS_RE.sub(lambda m: starters_text(original), text)

    # Convert .html links to plain text (internal nav links)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\.html\)", r"\1", text)

    # Convert blockquote attribution lines (>*Name or >*Name*) to HTML
    # so they render cleanly and can be styled separately from the quote.
    def fix_attribution(m):
        content = m.group(1)
        content = content.strip().strip("*").strip()
        refs = re.findall(r"\[\^[^\]]+\]", content)
        name = re.sub(r"\[\^[^\]]+\]", "", content).strip().rstrip(",")
        ref_str = "".join(refs)
        return f"> <span class='attribution'>{name.upper()}{ref_str}</span>"
    text = re.sub(r"^>\s*\*([^*].*?)(\*?)$", fix_attribution, text, flags=re.MULTILINE)

    return text.strip()


def md_to_html(md_text: str, prefix: str) -> str:
    result = subprocess.run(
        ["pandoc", "--from=markdown", "--to=html5",
         "--wrap=none", f"--id-prefix={prefix}-"],
        input=md_text, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"pandoc error: {result.stderr}", file=sys.stderr)
    html = result.stdout
    html = html.replace("<hr />", '<p class="section-break">§</p>')
    return html


PAPER_SIZES = {"letter": "letter", "a4": "A4"}

CSS_TEMPLATE = """\
@import url('https://fonts.googleapis.com/css2?family=Charmonman:wght@400;700&family=Nunito:ital,wght@0,400;0,600;0,700;1,400;1,600&display=swap');
@page {
    size: __PAGE_SIZE__;
    margin: 1in;
}
body {
    font-family: 'Nunito', 'Avenir Next', 'Avenir', system-ui, sans-serif;
    font-size: 14pt;
    line-height: 1.25;
    color: #1a1a1a;
}
section.essay {
    page-break-before: always;
}
section.essay:first-child {
    page-break-before: avoid;
}
h1 {
    font-family: 'Nunito', sans-serif;
    font-size: 54pt;
    font-weight: 700;
    margin-top: 0;
    margin-bottom: 0.5em;
}
h2 {
    font-family: 'Nunito', sans-serif;
    font-size: 24pt;
    font-weight: 700;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
}
p {
    margin-bottom: 0.8em;
}
blockquote {
    margin: 1em 1.5em;
    padding-left: 0.75em;
    border-left: 2pt solid #999;
    font-family: 'Charmonman', 'Quicksand', cursive;
    font-size: 24pt;
    font-style: normal;
}
blockquote ul {
    font-family: 'Charmonman', 'Quicksand', cursive;
}
a {
    color: #1a1a1a;
    text-decoration: underline;
}
section.footnotes {
    margin-top: 2em;
    padding-top: 0.5em;
    border-top: 1px solid #aaa;
    font-size: 10pt;
    line-height: 1.3;
}
section.footnotes hr { display: none; }
section.footnotes ol {
    padding-left: 1.5em;
}
.section-break {
    text-align: center;
    font-family: 'Charmonman', cursive;
    font-weight: 700;
    font-size: 24pt;
    margin: 1em 0;
}
pre, code {
    font-size: 10pt;
}
sup { font-size: 8pt; }
ul { margin-bottom: 0.8em; }
.attribution {
    font-family: 'Nunito', sans-serif;
    font-size: 10pt;
    font-style: normal;
    letter-spacing: 0.05em;
    float: right;
    margin-top: 0.3em;
}
"""


def render_pdf(filenames: list[str], output: Path, page_size: str = "letter"):
    css = CSS_TEMPLATE.replace("__PAGE_SIZE__", page_size)
    sections = []
    for filename in filenames:
        path = MD_DIR / filename
        if not path.exists():
            print(f"Skipping {filename}", file=sys.stderr)
            continue

        prefix = path.stem
        md = process_md(path)
        html = md_to_html(md, prefix)
        sections.append(f'<section class="essay">\n{html}\n</section>')

    full = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><style>{css}</style></head>
<body>
{"".join(sections)}
</body>
</html>"""

    from weasyprint import HTML
    HTML(string=full).write_pdf(str(output))
    print(f"PDF written to {output}")


if __name__ == "__main__":
    size_arg = sys.argv[2].lower() if len(sys.argv) > 2 else "letter"
    page_size = PAPER_SIZES.get(size_arg, size_arg)

    if len(sys.argv) > 1:
        name = Path(sys.argv[1]).name
        if not name.endswith(".md"):
            name += ".md"
        stem = Path(name).stem
        render_pdf([name], DESKTOP / f"{stem}.pdf", page_size)
    else:
        render_pdf(essay_order(), DESKTOP / "llama-essays.pdf", page_size)
