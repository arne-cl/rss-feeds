# Development / Testing
- Use `.venv/bin/python` and `.venv/bin/pip` (note the leading dot).
- Follow strict red/green TDD. Run `.venv/bin/pytest` before you change anything. Commit each phase separately in small increments.
- Don't re-fetch websites for testing parser changes! Use a saved page copy instead: `QUORA_PROFILE_HTML=<file> .venv/bin/python scripts/build_quora_feed.py`.
- Before building features/fixes on top of env secrets (e.g. `INSTAGRAM_SESSIONID`), verify they are set AND actually working — make a real test call with them and record the result in the ticket. Likewise, check recent build output/logs before assuming feed data is fine.

# Documentation
- Document every task in numbered markdown files in `./tickets`. Name open tickets `NNNN-todo-*.md`. Rename to `NNNN-done-*.md` after completion, commit again. Stay brief, but record every hurdle you had to overcome. Write/commit the first draft of the ticket before any implementation and update it during/after the implementation!


