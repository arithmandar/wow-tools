# Link Collector

A Chrome (Manifest V3) extension that collects link text and URLs into a list and exports them as a text file. Also works in Edge and Brave.

## Install

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked** and select this `link-collector` folder.

## Usage

Right-click a link, then choose one of:

| Menu item | Action |
|-----------|--------|
| **Save link text + URL** | Adds the link's text and target URL to the saved list. The toolbar badge shows the count. |
| **Export saved links to text file** | Downloads `links.txt` with one `text<TAB>URL` line per link. |
| **Clear saved links** | Empties the saved list. |

Export and Clear are also available when right-clicking on a page (not just a link).

## Output format

```
Example link text	https://example.com/page
Another link	https://example.org/
```

Tabs and newlines inside link text are replaced with spaces so each entry stays on one line.

## Notes

- Extensions can't append to an existing file. The list accumulates in extension storage and is written as a new file on each export (repeated exports are named `links (1).txt`, etc.).
- Image-only links have no text, so the link title or the URL is used instead.
- The saved list persists across browser restarts until cleared.

## Files

- `manifest.json` – extension manifest and permissions (`contextMenus`, `storage`, `downloads`).
- `background.js` – context menu handling, storage, and export.
- `content.js` – captures the link text on right-click.
