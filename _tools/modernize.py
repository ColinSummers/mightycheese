#!/usr/bin/env python3
"""
Modernize all HTML files in the Mighty Cheese site.
Strips Sandvox markup and wraps content in a modern HTML5 template.
"""

import os
import re
import sys
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {'_Resources', '_Media', '_tools', 'sandvox_Sunburst', 'sandvox_Imagine',
             'cgi-bin', '.git', '.claude', 'node_modules'}

NAV_ITEMS = [
    ('Home', 'index.html'),
    ('What', 'what.html'),
    ('Who', 'who.html'),
    ('Why', 'why.html'),
    ('Headaches', 'headaches/'),
    ('Pawlet Box', 'pog/the_pawlet_box/'),
]


def relative_root(file_path: Path) -> str:
    rel = file_path.relative_to(SITE_ROOT)
    depth = len(rel.parts) - 1
    if depth == 0:
        return ''
    return '../' * depth


def get_active_nav(file_path: Path) -> str:
    rel = str(file_path.relative_to(SITE_ROOT))
    if rel == 'index.html':
        return 'index.html'
    if rel.startswith('what'):
        return 'what.html'
    if rel.startswith('who'):
        return 'who.html'
    if rel.startswith('why'):
        return 'why.html'
    if rel.startswith('headaches/') or rel.startswith('migraines/') or rel.startswith('damage/'):
        return 'headaches/'
    if rel.startswith('pog/'):
        return 'pog/the_pawlet_box/'
    return ''


def extract_title(html: str) -> str:
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
    if not m:
        return 'Mighty Cheese'
    raw = m.group(1).strip()
    parts = [p.strip() for p in raw.split('|')]
    return parts[0] if parts else 'Mighty Cheese'


def extract_div_content(html: str, start_pos: int) -> tuple[str, int]:
    """Given html and a position right after an opening <div...> tag,
    extract the innerHTML up to its matching </div>, handling nesting."""
    depth = 1
    pos = start_pos
    while depth > 0 and pos < len(html):
        next_open = html.find('<div', pos)
        next_close = html.find('</div>', pos)

        if next_close == -1:
            break

        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
        else:
            depth -= 1
            if depth == 0:
                return html[start_pos:next_close], next_close + 6
            pos = next_close + 6

    return html[start_pos:], len(html)


def extract_main_content(html: str) -> str:
    pattern = r'<div\s+id="main-content"[^>]*>'
    m = re.search(pattern, html, re.IGNORECASE)
    if not m:
        return ''
    content, _ = extract_div_content(html, m.end())
    return content


def extract_index_section(content: str) -> tuple[str, str, str]:
    """Split content into before-index, index-content, after-index.
    Returns (before, index_inner, after) or (content, '', '') if no index."""
    pattern = r'<div\s+id="index"\s+class="(?:general|photogrid)-index">'
    m = re.search(pattern, content)
    if not m:
        return content, '', ''

    before = content[:m.start()]
    idx_inner, end_pos = extract_div_content(content, m.end())
    # Skip past any trailing comment
    rest = content[end_pos:]
    rest = re.sub(r'^\s*<!--[^>]*-->', '', rest)
    return before, idx_inner, rest


def transform_gallery_index(idx_inner: str) -> str:
    """Transform a gallery index into a grid or list."""
    # Check for thumbnails (photo galleries)
    thumbnails = re.findall(
        r'<a\s+href="([^"]+)">\s*<img[^>]*\bsrc="([^"]+)"[^>]*\balt="([^"]*)"[^>]*/?\s*>\s*</a>',
        idx_inner, re.DOTALL
    )

    if thumbnails:
        items = []
        for href, src, alt in thumbnails:
            items.append(
                f'<div class="gallery-item">'
                f'<a href="{href}"><img src="{src}" alt="{alt}" loading="lazy" /></a>'
                f'</div>'
            )
        return '<div class="gallery-grid">\n' + '\n'.join(items) + '\n</div>'

    # Text index (headaches, etc.)
    entries = list(re.finditer(
        r'<h3[^>]*><a\s+href="([^"]+)">(.*?)</a></h3>(.*?)(?=<h3|$)',
        idx_inner, re.DOTALL
    ))

    if not entries:
        return ''

    items = []
    for entry in entries:
        href = entry.group(1)
        title_html = entry.group(2)
        rest = entry.group(3)
        title = re.sub(r'<[^>]+>', '', title_html).strip()

        # Extract summary if present
        summary_match = re.search(
            r'class="article-summary"[^>]*>(.*?)</div>',
            rest, re.DOTALL
        )
        summary = summary_match.group(1).strip() if summary_match else ''

        li = f'<li><a href="{href}">{title}</a>'
        if summary:
            li += f'\n<div class="summary">{summary}</div>'
        li += '</li>'
        items.append(li)

    return '<ul class="index-list">\n' + '\n'.join(items) + '\n</ul>'


def clean_content(content: str) -> str:
    """Strip Sandvox cruft from extracted content."""

    # Remove main-top/main-bottom
    content = re.sub(r'<div\s+id="main-(?:top|bottom)">\s*</div>', '', content)

    # Remove all HTML comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

    # Strip Sandvox IDs
    content = re.sub(r'\s+id="k-[^"]*"', '', content)

    # Remove <span class="in"> wrappers (may be nested)
    for _ in range(3):
        content = re.sub(r'<span\s+class="in">(.*?)</span>', r'\1', content, flags=re.DOTALL)

    # Remove inline styles
    content = re.sub(r'\s+style="[^"]*"', '', content)

    # Clean br tags
    content = re.sub(r'<br\s+class="webkit-block-placeholder"\s*/?>', '<br />', content)

    # Remove empty elements
    content = re.sub(r'<div\s+class="callout-container">\s*</div>', '', content, flags=re.DOTALL)
    content = re.sub(r'<div\s+class="article-info">\s*</div>', '', content, flags=re.DOTALL)
    content = re.sub(r'<div\s+class="clear">\s*</div>', '', content)
    content = re.sub(r'<div\s+class="article-summary">\s*</div>', '', content)
    content = re.sub(r'<p>\s*<br\s*/?>\s*</p>', '', content)
    content = re.sub(r'<div>\s*<br\s*/?>\s*</div>', '', content)
    content = re.sub(r'<i>\s*</i>', '', content)
    content = re.sub(r'<div\s+class="caption">\s*</div>', '', content)

    # Unwrap RichTextElement
    content = re.sub(
        r'<div\s+class="RichTextElement">\s*<div>(.*?)</div>\s*</div>',
        r'\1', content, flags=re.DOTALL
    )
    content = re.sub(
        r'<div(?:\s+class="RichTextElement")>\s*(.*?)\s*</div>',
        r'\1', content, flags=re.DOTALL
    )

    # Unwrap article-content
    content = re.sub(
        r'<div\s+class="article-content">\s*',
        '', content
    )

    # Remove empty article-info with timestamp content (keep the timestamp)
    content = re.sub(
        r'<div\s+class="article-info">\s*<div\s+class="timestamp">\s*(.*?)\s*</div>\s*</div>',
        r'<p class="timestamp">\1</p>',
        content, flags=re.DOTALL
    )

    # Remove article wrapper divs (careful - just remove the opening tags
    # that contain article classes, the content is already extracted)
    content = re.sub(r'<div\s+class="article[^"]*">\s*', '', content)

    # Transform callout containers with content
    content = re.sub(r'<div\s+class="callout-top">\s*</div>', '', content)
    content = re.sub(r'<div\s+class="callout-bottom">\s*</div>', '', content)

    # Remove pagelet wrappers but keep content
    content = re.sub(r'<div\s+class="pagelet[^"]*">', '', content)
    content = re.sub(r'<div\s+class="pagelet-body">', '', content)
    content = re.sub(r'<div\s+class="elementIntroduction">', '', content)

    # Clean callout - unwrap
    content = re.sub(r'<div\s+class="callout">', '', content)
    content = re.sub(
        r'<div\s+class="callout-container">\s*(.*?)\s*</div>',
        lambda m: f'<div class="callout-content">{m.group(1)}</div>' if m.group(1).strip() else '',
        content, flags=re.DOTALL
    )

    # Fix stray closing divs from unwrapped elements - count opens vs closes
    # and remove excess closing divs
    content = balance_divs(content)

    # Clean excessive whitespace
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r'[ \t]+\n', '\n', content)

    return content.strip()


def balance_divs(html: str) -> str:
    """Remove excess closing </div> tags to balance the HTML."""
    # Simple approach: track open/close divs and remove unmatched closes
    result = []
    depth = 0
    pos = 0

    while pos < len(html):
        # Check for opening div
        open_match = re.match(r'<div[\s>]', html[pos:])
        close_match = re.match(r'</div\s*>', html[pos:])

        if open_match:
            depth += 1
            # Find end of opening tag
            end = html.find('>', pos) + 1
            result.append(html[pos:end])
            pos = end
        elif close_match:
            if depth > 0:
                depth -= 1
                result.append(close_match.group())
            # else: skip unmatched closing div
            pos += close_match.end()
        else:
            result.append(html[pos])
            pos += 1

    return ''.join(result)


def build_nav(root_prefix: str, active: str) -> str:
    items = []
    for label, href in NAV_ITEMS:
        cls = ' class="active"' if href == active else ''
        full_href = root_prefix + href
        items.append(f'          <li{cls}><a href="{full_href}">{label}</a></li>')
    return '\n'.join(items)


def make_page(title: str, nav_html: str, content: str, root_prefix: str) -> str:
    css_path = root_prefix + 'style.css'
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} | Mighty Cheese</title>
  <meta name="author" content="Colin Summers" />
  <link rel="stylesheet" href="{css_path}" />
</head>
<body>
  <nav class="navbar">
    <div class="navbar-inner">
      <a class="navbar-brand" href="{root_prefix or './'}">Mighty Cheese</a>
      <input type="checkbox" id="nav-toggle" class="nav-toggle" />
      <label for="nav-toggle" class="nav-toggle-label"><span></span></label>
      <ul class="nav-links">
{nav_html}
      </ul>
    </div>
  </nav>
  <main>
{content}
  </main>
  <footer>
    <p>Copyright Colin Summers 2006 and other years.</p>
  </footer>
</body>
</html>
'''


def process_file(file_path: Path, original_html: str) -> bool:
    """Process a single HTML file from its original content. Returns True if modified."""
    html = original_html

    # Skip non-Sandvox files
    if 'sandvox' not in html.lower() and 'main-content' not in html:
        return False

    title = extract_title(html)
    main_content = extract_main_content(html)

    if not main_content:
        print(f"  WARNING: No main-content found in {file_path}")
        return False

    # Separate index section if present
    before_idx, idx_inner, after_idx = extract_index_section(main_content)

    # Transform index section
    if idx_inner:
        idx_html = transform_gallery_index(idx_inner)
        content = before_idx + '\n' + idx_html + '\n' + after_idx
    else:
        content = main_content

    # Clean the content
    content = clean_content(content)

    # Build page
    root_prefix = relative_root(file_path)
    active = get_active_nav(file_path)
    nav_html = build_nav(root_prefix, active)
    output = make_page(title, nav_html, content, root_prefix)

    file_path.write_text(output, encoding='utf-8')
    return True


def main():
    # First, read all original files into memory before modifying anything
    print(f"Site root: {SITE_ROOT}")

    files = []
    for path in sorted(SITE_ROOT.rglob('*.html')):
        rel = path.relative_to(SITE_ROOT)
        parts = rel.parts
        skip = False
        for skip_dir in SKIP_DIRS:
            if any(p == skip_dir for p in parts[:-1]):
                skip = True
                break
        # Also skip pog/Media
        if str(rel).startswith('pog/Media'):
            skip = True
        if not skip:
            files.append(path)

    print(f"Found {len(files)} HTML files to process")

    # We need the originals since we already ran the first pass
    # But we already overwrote them... We need to use git to restore first
    # Check if we have the originals
    sample = files[0].read_text(encoding='utf-8', errors='replace')
    if '<!DOCTYPE html>' in sample[:50] and 'navbar' in sample[:500]:
        print("\nFiles already modernized. Restoring originals from git first...")
        import subprocess
        # Restore all HTML files from git
        result = subprocess.run(
            ['git', 'checkout', 'HEAD', '--', '.'],
            cwd=SITE_ROOT,
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Git restore failed: {result.stderr}")
            return
        print("Restored originals from git.\n")

    # Now re-scan since files are restored
    originals = {}
    for path in files:
        try:
            originals[path] = path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            print(f"  ERROR reading {path}: {e}")

    print(f"Read {len(originals)} files\n")

    modified = 0
    for path in files:
        if path not in originals:
            continue
        rel = path.relative_to(SITE_ROOT)
        result = process_file(path, originals[path])
        if result:
            modified += 1
            print(f"  OK  {rel}")

    print(f"\nDone: {modified} modified out of {len(files)} files")


if __name__ == '__main__':
    main()
