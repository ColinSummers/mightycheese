#!/usr/bin/env python3
"""Replace broken external links in voltaday posts with dead-link dialog triggers.

Each broken link gets its own dialog showing the original URL.
"""

import re
import hashlib
import html as htmlmod
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
VOLTADAY = BASE / 'cts' / 'voltaday'

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


def fix_file(fpath):
    content = fpath.read_text()
    original = content

    # First remove any old broken-link dialogs from previous run
    content = re.sub(r'\s*<div id="broken-link" class="broken-link-dialog">.*?</div>\s*</div>\s*</div>', '', content, flags=re.DOTALL)
    # Also revert old dead-link replacements to get original URLs back
    content = re.sub(r'<a href="#broken-link" class="dead-link"', '<a href="__RESTORE__" class="dead-link"', content)

    # Apply benign redirects
    for old_url, new_url in BENIGN_REDIRECTS.items():
        if old_url in content:
            content = content.replace(old_url, new_url)

    # Collect dead links and replace them
    dead_urls_found = set()

    def replace_dead(m):
        href = m.group(1)
        attrs = m.group(2)
        if is_dead(href):
            dead_urls_found.add(href)
            aid = anchor_id(href)
            return f'<a href="#{aid}" class="dead-link"{attrs}>'
        return m.group(0)

    content = re.sub(r'<a\s+href="([^"]+)"([^>]*)>', replace_dead, content)

    # Remove placeholder restores that didn't match (shouldn't happen but be safe)
    content = content.replace('__RESTORE__', '#broken-link')

    # Add dialogs before </main>
    if dead_urls_found:
        dialogs = '\n'.join(make_dialog(u) for u in sorted(dead_urls_found))
        # Remove any stale dialogs
        content = re.sub(r'\s*<div id="dead-[0-9a-f]+" class="broken-link-dialog">.*?</div>\s*</div>\s*</div>', '', content, flags=re.DOTALL)
        content = content.replace('</main>', f'{dialogs}\n  </main>')

    if content != original:
        fpath.write_text(content)
        return True
    return False


def main():
    count = 0
    for fpath in sorted(VOLTADAY.glob('posts/*.html')):
        if fix_file(fpath):
            count += 1
            print(f'  Fixed: {fpath.name}')
    for fpath in sorted(VOLTADAY.glob('*.html')):
        if fix_file(fpath):
            count += 1
            print(f'  Fixed: {fpath.name}')
    print(f'\n{count} files updated')


if __name__ == '__main__':
    main()
