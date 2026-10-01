# 0004: Scrub secrets from saved-page fixtures + pre-push secret scan

## Problem

`git push` was rejected by GitHub push protection (second occurrence): a
saved-page fixture (`tests/fixtures/klum-pages/wupsi-offiziele-anfrage-handy.html`,
added in `ea4db99`) contains a Duda boilerplate Mapbox `pk.eyJ1Ijoi...` token
plus Here `appId`/`appCode`. All 11 unpushed commits carry the blob.

## Approach

1. Sanitize the fixture: replace Mapbox token, Here appId/appCode and
   Snowplow appId values with `REDACTED-FOR-FIXTURE`; keep the HTML intact
   for parser tests.
2. Rewrite the 11 unpushed commits: interactive rebase with `edit` at
   `ea4db99`, amend the sanitized fixture in, continue. Safe because none of
   these commits is on the remote yet.
3. Prevention: committed `.githooks/pre-push` scanning added lines of the
   outgoing range (`git diff --branches --not --remotes`) for common secret
   patterns (Mapbox, AWS, GitHub, Google, Slack, private keys). Activate via
   `git config core.hooksPath .githooks`.

## Status

todo
