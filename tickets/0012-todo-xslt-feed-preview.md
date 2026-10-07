# 0012: XSLT preview stylesheet for local feed files in Firefox

## Problem

The Instagram feeds embed every carousel slide as HTML in
`content:encoded` (ticket 0011), but feed readers render that
inconsistently (some only show the enclosure = cover slide). For
reviewing the generated `feeds/*.xml` locally it would be nice if
Firefox showed the feeds as a readable page — including all slides and
`<video>` tags — instead of the raw XML tree.

Firefox applies `<?xml-stylesheet type="text/xsl" href="…"?>` to XML
documents, so the plan is a stylesheet + that PI in the generated feeds.

## Constraints / decisions

- Firefox ships only XSLT 1.0 (Transformiix) and does **not** support
  `disable-output-escaping`, so pure XSLT cannot re-render the escaped
  HTML inside `content:encoded`.
- XSLT output `method="html"` *does* run inline `<script>` in Firefox,
  even on `file://` URLs. Decision (user-confirmed): tiny inline JS
  injects the `content:encoded` text of each item via `innerHTML`;
  a `<noscript>` fallback shows enclosure image + plain description.
- The PI href is relative (`feed-preview.xsl`) and the stylesheet lives
  in `feeds/` next to the XMLs — Firefox allows file:// documents to
  load stylesheets from their own directory. User-confirmed scope: the
  PI is added centrally in `common.build_feed()` for **all** feeds.
- `raw.githubusercontent.com` serves XML as `text/plain`, so remote
  subscribers never trigger the stylesheet — the PI is inert for them.
- Instagram CDN URLs expire (`oe=` param, ~2 weeks): older slides may
  403 in the preview; alt text shows instead.

## Plan

1. Red tests in `tests/test_common.py`: `build_feed()` output carries
   the PI right after the XML declaration; `load_previous()` round-trip
   on a PI-bearing feed still restores items.
2. Green: PI injection + `feeds/feed-preview.xsl` (channel header, item
   title/date/link, hidden raw-content div, JS injection, CSS).
3. Regenerate one feed offline from a saved fixture so a committed
   `feeds/*.xml` carries the PI; README note.

## Hurdles

- (to be filled during implementation)

## Status

todo
