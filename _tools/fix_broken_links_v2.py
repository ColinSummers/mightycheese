#!/usr/bin/env python3
"""Recover original URLs from WordPress export and rebuild per-link dead-link dialogs.

The first pass of fix_broken_links.py replaced dead URLs with #broken-link,
losing the original URL. This script recovers them from the WordPress export,
then applies the new per-link dialog approach.
"""

import re
import hashlib
import html as htmlmod
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
VOLTADAY = BASE / 'cts' / 'voltaday'
XML_PATH = BASE / 'voltaday.WordPress.2026-05-16.xml'

DEAD_URLS = [
    'http://twitter.com',
    'https://twitter.com/voltaday',
    'http://chevrolet.posterous.com/',
    'http://gmvoltcab.com',
    'http://www.gmvoltcab.com/',
    'http://www.hoomanchevy.com/',
    'http://blogs.consumerreports.org/',
    'https://salsa.democracyinaction.org/',
    'http://nissan-leaf.net/',
    'http://silkbaron.com/',
    'http://solarchargeddriving.com',
    'http://support.nest.com/',
    'http://www.atvn.org/',
    'http://www.autoweek.com/article/20101028/',
    'http://www.eurekalert.org/',
    'http://www.greencarreports.com/blog/1052107',
    'http://www.palladiumboots.com/',
    'http://www.toyota.com/esq/',
    'http://www.wired.com/autopia/',
    'http://detnews.com/',
    'http://pressroom.toyota.com/',
    'http://www.freep.com/',
    'http://www.nytimes.com/2010/',
    'https://www.truecar.com/',
    'http://vimeo.com/15428968',
    'http://cosmiclog.msnbc.msn.com/',
    'http://voltage.com',
    'http://solarcity.com',
    'http://tommywood.com',
    'http://www.washingtonpost.com/wp-dyn/',
    'http://www.getmyvolt.com',
    'http://access.toyota.com',
    'http://chevroletvoltage.com/',
    'http://www.chevroletvoltage.com/',
    'http://nest.com',
    'http://content.usatoday.com/',
    'http://www.santamonicafurnaceandairconditioning.com',
]

BENIGN_REDIRECTS = {
    'http://www.altcarexpo.com/': 'https://altcarexpo.org/',
    'http://www.gizmag.com/sahara-solar-breeder-project/17054/': 'https://newatlas.com/sahara-solar-breeder-project/17054/',
    'http://www.useit.com/jakob/': 'https://www.nngroup.com/people/jakob-nielsen/',
}


def is_dead(href):
    for prefix in DEAD_URLS:
        if href.startswith(prefix) or href.rstrip('/').startswith(prefix.rstrip('/')):
            return True
    return False


def anchor_id(url):
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    return f'dead-{h}'


def make_dialog(url):
    aid = anchor_id(url)
    escaped = htmlmod.escape(url)
    return f'''<div id="{aid}" class="broken-link-dialog">
  <div class="broken-link-dialog-box">
    <p><strong>Broken Link</strong></p>
    <p>The web is fragile and this link is no longer pointing to the correct content.</p>
    <p class="dead-url">{escaped}</p>
    <a href="#" class="dismiss">OK</a>
  </div>
</div>'''


def parse_wp_posts():
    """Parse WordPress export and return {slug: content} mapping."""
    tree = ET.parse(XML_PATH)
    root = tree.getroot()
    ns = {'wp': 'http://wordpress.org/export/1.2/'}
    posts = {}
    for item in root.findall('.//item'):
        ptype = item.find('wp:post_type', ns)
        if ptype is None or ptype.text != 'post':
            continue
        slug = item.find('wp:post_name', ns).text or ''
        content = ''
        for child in item:
            if 'encoded' in child.tag:
                content = child.text or ''
                break
        posts[slug] = content
    return posts


def find_dead_links_in_wp(content):
    """Find all dead links in WordPress content, return {link_text: url} mapping."""
    links = {}
    for m in re.finditer(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', content, re.DOTALL):
        href = m.group(1)
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if is_dead(href):
            links[text] = href
    return links


def fix_file(fpath, wp_posts):
    slug = fpath.stem
    wp_content = wp_posts.get(slug, '')
    if not wp_content:
        return False

    content = fpath.read_text()
    original = content

    # Check if this file has old-style broken links
    if '#broken-link' not in content:
        return False

    # Get the dead link text->url mapping from WordPress
    dead_links = find_dead_links_in_wp(wp_content)
    if not dead_links:
        return False

    # Remove old single dialog
    content = re.sub(
        r'\s*<div id="broken-link" class="broken-link-dialog">.*?</div>\s*</div>\s*</div>',
        '', content, flags=re.DOTALL
    )
    # Also remove any stale per-link dialogs from earlier attempts
    content = re.sub(
        r'\s*<div id="dead-[0-9a-f]+" class="broken-link-dialog">.*?</div>\s*</div>\s*</div>',
        '', content, flags=re.DOTALL
    )

    dead_urls_found = set()

    # Replace each dead-link anchor by matching link text to original URL
    def replace_dead_link(m):
        text_raw = m.group(1)
        text_clean = re.sub(r'<[^>]+>', '', text_raw).strip()
        if text_clean in dead_links:
            url = dead_links[text_clean]
            dead_urls_found.add(url)
            aid = anchor_id(url)
            return f'<a href="#{aid}" class="dead-link">{text_raw}</a>'
        return m.group(0)

    content = re.sub(
        r'<a href="#broken-link" class="dead-link"[^>]*>(.*?)</a>',
        replace_dead_link, content, flags=re.DOTALL
    )

    # Add new per-link dialogs before </main>
    if dead_urls_found:
        dialogs = '\n'.join(make_dialog(u) for u in sorted(dead_urls_found))
        content = content.replace('</main>', f'{dialogs}\n  </main>')

    if content != original:
        fpath.write_text(content)
        return True
    return False


def main():
    wp_posts = parse_wp_posts()
    print(f'Parsed {len(wp_posts)} posts from WordPress export')

    count = 0
    unmatched = []
    for fpath in sorted(VOLTADAY.glob('posts/*.html')):
        if '#broken-link' in fpath.read_text():
            if fix_file(fpath, wp_posts):
                count += 1
                print(f'  Fixed: {fpath.name}')
            else:
                unmatched.append(fpath.name)

    # Also fix index pages
    for fpath in sorted(VOLTADAY.glob('*.html')):
        if '#broken-link' in fpath.read_text():
            # Index pages don't have slugs matching WP posts, skip
            pass

    if unmatched:
        print(f'\n  Could not fix: {", ".join(unmatched)}')
    print(f'\n{count} files updated')


if __name__ == '__main__':
    main()
