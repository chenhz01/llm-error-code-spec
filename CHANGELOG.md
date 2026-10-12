# Changelog — llm-error-code-spec

All releases are local drafts; no remote operations are performed.

## v0.1.1 — 2026-10-13

Fixed:
- default_exit range widened to [1,125]; `map` falls back to the bundled sample registry.

Changed:
- self_test expanded to >=60 cases across functional / exception / extreme-edge
  categories (scaffold v2 four defenses: SystemExit capture, Unicode-safe
  matching, Windows newline-safe fixtures, SUMMARY last line).
- README: added Performance section with [Measured] numbers and in-repo
  reproduction commands.

## v0.1.0 — 2026-10-13

Added:
- Initial local draft: LLM gateway error taxonomy + exit-code mapping + registry consistency suite.
- argparse CLI (pure standard library), self_test.py, MIT LICENSE.
