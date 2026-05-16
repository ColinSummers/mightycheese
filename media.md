# Mightycheese Media on R2

The four pages moved from flyingsummers (FHR Condo, Home Movies: Super8, Drone, Atari) have their images and videos stored in Cloudflare R2:

- Bucket: `flyingsummers-media`
- Path: `cheese/`
- Public URL: `https://pub-2e58c6df17c64bd492e25a414243b1b7.r2.dev/cheese/`

The local copies of these pages are in `flyingsummers-pages/` with their media in `flyingsummers-pages/images/` and `flyingsummers-pages/videos/`. When rebuilding them into mightycheese proper, update image/video paths to point at the R2 `cheese/` prefix.

## URL patterns

Images:
```html
<img src="https://pub-2e58c6df17c64bd492e25a414243b1b7.r2.dev/cheese/images/filename.jpg" />
```

Videos:
```html
<video controls preload="metadata" poster="https://pub-2e58c6df17c64bd492e25a414243b1b7.r2.dev/cheese/videos/posters/filename.jpg">
  <source src="https://pub-2e58c6df17c64bd492e25a414243b1b7.r2.dev/cheese/videos/filename.mov" />
</video>
```

The base URL for all media is `https://pub-2e58c6df17c64bd492e25a414243b1b7.r2.dev/cheese/`, followed by the same relative path structure as the local files.

## Uploading to R2

rclone is already installed and configured with a remote named `r2` pointing at the `flyingsummers-media` bucket. To upload the cheese media:

```bash
cd /Users/colin/Sites/github_pages/mightycheese
rclone sync flyingsummers-pages/images/ r2:flyingsummers-media/cheese/images/ --progress
rclone sync flyingsummers-pages/videos/ r2:flyingsummers-media/cheese/videos/ --progress
```

No API keys needed — rclone config is at `~/.config/rclone/rclone.conf`.

## Current state

The `cheese/` folder exists in the R2 bucket but is empty — the media files have NOT been uploaded yet. Run the rclone commands above to populate it.
