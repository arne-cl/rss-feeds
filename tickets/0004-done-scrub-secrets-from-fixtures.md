# 0004: Scrub secrets from saved-page fixtures + pre-push secret scan

## Problem

`git push` was rejected by GitHub push protection (second occurrence): a
saved-page fixture (`tests/fixtures/klum-pages/wupsi-offiziele-anfrage-handy.html`,
added in `ea4db99`) contains a Duda boilerplate Mapbox `pk.eyJ1Ijoi...` token
plus Here `appId`/`appCode`. All 11 unpushed commits carry the blob.

## Approach

1. Sanitize the fixture: replace Mapbox token and Here appId/appCode with
   `REDACTED-FOR-FIXTURE`; keep the HTML intact for parser tests.
2. Rewrite the 11 unpushed commits: interactive rebase with `edit` at
   `ea4db99`, amend the sanitized fixture in, continue. Safe because none of
   these commits is on the remote yet.
3. Prevention: committed `.githooks/pre-push` scanning added lines of all
   local-only commits (`git rev-list --branches --not --remotes`) for common
   secret patterns (Mapbox, AWS, GitHub, GitLab, Google, Slack, private
   keys). Activate via `git config core.hooksPath .githooks`.

## Hurdles

- The Snowplow `appId: 353ca308...` and the `353ca308...` occurrences elsewhere
  in the fixture are the Duda *site alias* — public URL data the parser
  depends on, not a secret. Left untouched.
- `tests/fixtures/klum-news.html` also contains the Here appCode, but that
  blob is already pushed (commit `9262878`); push protection only scans new
  pushes, so it stays as-is. Rewriting pushed history was not worth it.
- The pattern list needs `{30,}`-style length anchors: the ticket prose itself
  quotes the `pk.eyJ1Ijoi...` token prefix, and a loose pattern would flag it.
- First hook negative test was invalid (fake secret file was created outside
  the repo, so the commit and hook never ran). Re-tested with the file inside
  the repo: hook correctly exits 1 naming the commit and pattern.

## Verification

- `venv/bin/pytest`: 74 passed (before and after scrub + rebase).
- `git grep` over `origin/main..main`: no Mapbox token in any unpushed commit.
- Hook passes on the real outgoing range, rejects a planted fake `AKIA…` key.

## Status

done
