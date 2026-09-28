# rss-feeds

RSS feeds generated from pages that don't offer one.

## Feeds

| Feed | URL |
|------|-----|
| Alan Kay on Quora | `https://raw.githubusercontent.com/arne-cl/rss-feeds/main/feeds/alankay-quora.xml` |

Subscribe with the raw URL above — most RSS readers accept it as-is.

## How it works

Quora blocks plain HTTP clients, so `scripts/build_feed.py`:

1. Fetches the profile page directly using Chrome TLS impersonation
   (`curl_cffi`) and extracts the answer objects embedded in the page's JSON
   blobs — this yields the full answer text but no dates.
2. If that fails or yields nothing, falls back to the
   [r.jina.ai](https://jina.ai/reader) reader proxy and parses the rendered
   DOM, which gives excerpts plus the answer dates shown on the profile.
3. Merges new items into `feeds/alankay-quora.xml` (deduped by permalink,
   newest first, capped at 100) so history survives between runs. Known items
   keep their previously stored dates.

The feed is refreshed weekly by
[.github/workflows/update.yml](.github/workflows/update.yml) (Mondays 06:17
UTC), which commits the updated XML if anything changed. Trigger it manually
via the Actions tab → "Update feeds" → "Run workflow".

If the jina.ai fallback gets rate-limited on GitHub's shared runner IPs, add a
free [jina.ai API key](https://jina.ai/reader) as the repository secret
`JINA_API_KEY`.

## Local development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_feed.py
```

Set `QUORA_PROFILE_HTML=<file>` to run against a saved page copy instead of fetching Quora.

