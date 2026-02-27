# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static HTML website for mightycheese.com, a personal site by Colin Summers. Originally built with Sandvox (Mac website builder), modernized in 2026 to HTML5 with responsive CSS. Hosted on Cloudflare Pages.

## Development

There is no build system, package manager, or dev server. The site is pure static HTML/CSS with no JavaScript. Files are served as-is.

To preview locally: `python3 -m http.server`

## Architecture

- **style.css** — Single site-wide stylesheet (CSS variables, flexbox layout, responsive, CSS-only hamburger menu)
- **Root HTML files** — Main site pages (index.html, what.html, who.html, why.html, and ~27 other content pages)
- **headaches/** — Blog-like archive (2004–2007) with yearly subdirectories and RSS feeds (index.xml)
- **migraines/** — Additional headache content with yearly subdirectories
- **pog/** — Photo gallery collections (the_pawlet_box/, the_pawlet_box_2/, pawlet/) with CSS grid thumbnails
- **damage/** — Additional content section
- **media/** — Site-wide images (pawlet thumbnails, cheese photos, etc.)
- **_tools/** — Build/migration scripts (modernize.py)

## Conventions

- HTML5 doctype with UTF-8 encoding
- Responsive viewport (`width=device-width, initial-scale=1.0`)
- Single stylesheet: `style.css` (linked with relative paths based on directory depth)
- All pages share a common navbar and footer template
- No JavaScript is used anywhere on the site
- Gallery index pages use CSS Grid for thumbnail layout
- Cheese-themed color palette using CSS custom properties

## Deployment

Cloudflare Pages — no build step needed. Just serve the root directory as static files.
