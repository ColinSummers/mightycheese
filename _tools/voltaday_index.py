#!/usr/bin/env python3
"""Generate card-based index pages for the Volt a Day blog from WordPress export."""

import xml.etree.ElementTree as ET
import re
import html
import sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
OUT_DIR = BASE / 'cts' / 'voltaday'
MEDIA_PREFIX = '../../media/voltaday'

PAGE_GROUPS = [
    ('index.html', 'September 2010', lambda d: d.startswith('2010-09')),
    ('october-2010.html', 'October 2010', lambda d: d.startswith('2010-10')),
    ('november-2010.html', 'November 2010', lambda d: d.startswith('2010-11')),
    ('december-2010-on.html', 'December 2010 &amp; Beyond', lambda d: d >= '2010-12'),
]


def parse_posts(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = {'wp': 'http://wordpress.org/export/1.2/'}
    posts = []
    for item in root.findall('.//item'):
        ptype = item.find('wp:post_type', ns)
        status = item.find('wp:status', ns)
        if ptype is None or ptype.text != 'post':
            continue
        if status is None or status.text != 'publish':
            continue
        title = item.find('title').text or ''
        slug = item.find('wp:post_name', ns).text or ''
        date_str = item.find('wp:post_date', ns).text or ''
        content = ''
        for child in item:
            if 'encoded' in child.tag:
                content = child.text or ''
                break
        posts.append({
            'title': title,
            'slug': slug,
            'date': date_str,
            'content': content,
        })
    posts.sort(key=lambda x: x['date'])
    return posts


def get_first_image(content):
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    if m:
        url = m.group(1)
        m2 = re.search(r'uploads/(\d{4}/\d{2}/[^"\'?\s]+)', url)
        if m2:
            return f'{MEDIA_PREFIX}/{m2.group(1)}'
    return None


def get_excerpt(content, max_len=180):
    text = re.sub(r'\[.*?\]', '', content)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    truncated = len(text) > max_len
    if truncated:
        text = text[:max_len].rsplit(' ', 1)[0] + '…'
    return html.escape(text), truncated


def format_date(date_str):
    try:
        dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
        return dt.strftime('%B %d, %Y')
    except (ValueError, TypeError):
        return date_str[:10]


def has_post_file(slug):
    return (OUT_DIR / 'posts' / f'{slug}.html').exists()


def make_card(post):
    img = get_first_image(post['content'])
    excerpt, truncated = get_excerpt(post['content'])
    date = format_date(post['date'])
    slug = post['slug']
    title_esc = html.escape(post['title'])
    has_file = has_post_file(slug)
    link = f'posts/{slug}.html' if has_file else '#'

    if img:
        thumb = f'<div class="blog-card-thumb"><a href="{link}"><img src="{img}" alt="" loading="lazy" /></a></div>\n'
        cls = 'blog-card'
    else:
        thumb = ''
        cls = 'blog-card text-only'

    title_html = f'<a href="{link}">{title_esc}</a>' if has_file else title_esc
    readmore = ''
    if truncated and has_file:
        readmore = f' <a href="{link}" class="read-more">read&nbsp;more</a>'

    return f'''<article class="{cls}">
{thumb}<div class="blog-card-body">
<h3>{title_html}</h3>
<div class="blog-card-date">{date}</div>
<div class="blog-card-excerpt">{excerpt}{readmore}</div>
</div>
</article>'''


NAV_TEMPLATE = '''<nav class="blog-nav">
{prev}
{next}
</nav>'''


def make_nav(page_idx):
    prev_link = ''
    next_link = ''
    if page_idx > 0:
        pfile, ptitle, _ = PAGE_GROUPS[page_idx - 1]
        prev_link = f'<a href="{pfile}">&larr; {ptitle}</a>'
    if page_idx < len(PAGE_GROUPS) - 1:
        nfile, ntitle, _ = PAGE_GROUPS[page_idx + 1]
        next_link = f'<a href="{nfile}">{ntitle} &rarr;</a>'
    if not prev_link:
        prev_link = '<span></span>'
    if not next_link:
        next_link = '<span></span>'
    return NAV_TEMPLATE.format(prev=prev_link, next=next_link)


PAGES_NAV = '<p class="voltaday-pages"><strong>Blog</strong> | <a href="about.html">About</a> | <a href="cars.html">Cars</a> | <a href="test-drives.html">Test Drives</a></p>'


def make_page(page_title, cards_html, page_idx):
    nav_bottom = make_nav(page_idx)
    nav_top = make_nav(page_idx) if page_idx > 0 else ''
    pages_nav = PAGES_NAV if page_idx == 0 else ''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Mighty Cheese | Volt a Day | {html.escape(page_title)}</title>
  <meta name="author" content="Colin Summers" />
  <link rel="stylesheet" href="../../style.css" />
</head>
<body>
  <nav class="navbar">
    <div class="navbar-inner">
      <a class="navbar-brand" href="../../">MightyCheese</a>
      <input type="checkbox" id="nav-toggle" class="nav-toggle" />
      <label for="nav-toggle" class="nav-toggle-label"></label>
      <ul class="nav-links">
          <li><a href="../../what.html">What</a></li>
          <li><a href="../../who.html">Who</a></li>
          <li><a href="../../why.html">Why</a></li>
      </ul>
    </div>
  </nav>
  <main>
<h2><a href="../">cts</a> | <a href="./">Volt a Day</a> | {page_title}</h2>
{pages_nav}
{nav_top}
{cards_html}
{nav_bottom}
  </main>
  <footer>
    <p>Copyright Colin Summers 2006 and other years.</p>
  </footer>
</body>
</html>
'''


def main():
    candidates = sorted(BASE.glob('voltaday.WordPress.*.xml'))
    if not candidates:
        print(f'No voltaday.WordPress.*.xml found in {BASE}', file=sys.stderr)
        return 1
    xml_path = candidates[-1]

    posts = parse_posts(xml_path)
    print(f'Parsed {len(posts)} posts from {xml_path.name}')

    for idx, (filename, title, filter_fn) in enumerate(PAGE_GROUPS):
        page_posts = [p for p in posts if filter_fn(p['date'][:10])]
        cards = '\n'.join(make_card(p) for p in page_posts)
        page_html = make_page(title, cards, idx)
        out_path = OUT_DIR / filename
        out_path.write_text(page_html)
        print(f'  {filename}: {len(page_posts)} entries')


if __name__ == '__main__':
    main()
