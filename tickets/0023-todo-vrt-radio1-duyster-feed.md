# 0023: Podcast feed for VRT Radio 1 "Duyster"

## Problem

The Radio 1 music show "Duyster" (Ayco Duyster,
https://www.vrt.be/vrtmax/luister/radio/d/duyster~11-177/) is not
published as a podcast by VRT. We want an RSS feed with audio
enclosures like the BRF1 show feeds (tickets 0006/0022).

## Findings (site research, all verified live 2026-11-15)

- The VRT MAX page is fully client-rendered; data comes from a public
  GraphQL API `https://www.vrt.be/vrtnu-api/graphql/public/v1`
  (no auth; introspection disabled but full query text embedded in the
  webpack bundles — extracted from the lazy route chunks).
- `ProgramPage` query, `pageId = "/vrtmax/luister/radio/d/duyster~11-177/"`
  (the URL path!) returns the "Uitzendingen" tab as a `PaginatedTileList`
  of `RadioEpisodeTile`s: title ("DUYSTER."), link
  (`.../duyster~11-39811-0/`), description, cover, duration.
  **Only ~10 recent broadcasts** (`hasNextPage: false`) — VRT purges old
  episodes, so the feed must accumulate via the existing merge logic.
- Tile dates are display strings ("Maandag 9 november") without a year.
  `EpisodePage` query (same pageId pattern per episode) provides
  `player.modes[0].broadcastStartDate` ("2026-11-09T21:00:00.000Z"),
  SEO title with full date ("DUYSTER. - maandag 9 november 2026 om
  22:00"), and the media `streamId`
  (`pbs-pub-…$aud-…`).
- Media resolution (same recipe as yt-dlp's VRT extractor):
  POST `/vualto-video-aggregator-web/rest/external/v2/tokens` with an
  HS256 JWT `playerInfo` signed with the static player key from the
  public player JS (prod key `2a9251d7…`, kid `0-0Fp51UZyk…`) →
  `vrtPlayerToken` → GET `…/v2/videos/{streamId}` → `targetUrls`:
  HLS `.m3u8` + DASH `.mpd` (ondemand-radio.vrtcdn.be, unsigned/stable
  path, no token needed afterwards).
- **No direct MP3 exists** (segments are AAC in MPEG-TS). User decision:
  enclosure = HLS URL, `type="application/vnd.apple.mpegurl"` (plays in
  VLC, AntennaPod, Apple ecosystem).
- Show metadata: brand radio1, presenter "Ayco Duyster", cover
  `https://images.vrt.be/orig/2025/02/05/c26e5909-134d-4fe2-9e44-0e68c6d9f700.png`.

## Approach

New standalone `scripts/build_vrt_radio1_duyster_feed.py` on top of
`scripts/common.py` (fetch/merge/warning/feed assembly); VRT's GraphQL
stack shares nothing with the BRF1 WordPress theme, so no new shared
module. Mirrors the BRF1 mechanics: parse tile list, enrich *new* items
only (enclosure present ⇒ cached), soft-failure warning item, merge,
write. Offline mode via env vars: `VRT_DUYSTER_PROGRAM_JSON`,
`VRT_DUYSTER_EPISODES_DIR`, `VRT_DUYSTER_MEDIA_DIR`.

Feed: `feeds/vrt-radio1-duyster.xml`, title "Duyster (VRT Radio 1)",
language `nl`, itunes author "VRT Radio 1", category Music, explicit no.

## Hurdles

- GraphQL query text lives as JS string in webpack chunk 6545
  (ProgramPage) / 1639 (EpisodePage); strings end at the first
  *unescaped* quote.
- Tokens endpoint: `clientId` query params and `videos/` vs older
  `media/` paths 404; the working recipe needs no clientId at all and
  POSTs a JWT-signed `playerInfo` (exp now+900).
- Tile titles are all identical "DUYSTER." → use the enriched
  episode-page title (contains date) for uniqueness.

## Status

- [x] ticket draft committed
- [ ] fixtures from live responses
- [ ] tests red
- [ ] builder green
- [ ] wired into update_local.sh + README, live build
- [ ] ticket done
