# Development / Testing
- Use `venv/bin/python` and `venv/bin/pip`.
- Follow strict red/green TDD. Run `venv/bin/pytest` before you change anything. Commit each phase separately in small increments.
- Don't re-fetch websites for testing parser changes! Use a saved page copy instead: `QUORA_PROFILE_HTML=<file> python scripts/build_feed.py`.

# Documentation
- Document every task in numbered markdown files in `./tickets`. Name open tickets `NNNN-todo-*.md`. Rename to `NNNN-done-*.md` after completion, commit again. Stay brief, but record every hurdle you had to overcome. Write/commit the first draft of the ticket before any implementation and update it during/after the implementation!


