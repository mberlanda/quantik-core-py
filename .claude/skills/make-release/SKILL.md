---
name: make-release
description: Use when preparing, validating, documenting, or publishing a quantik-core release. Covers branch setup, version and metadata updates, changelog/docs checks, local quality gates, artifact validation, PR review, tagging, and PyPI/GitHub release handoff.
---

# Make Release

Use this skill for release work in `quantik-core-py`, especially requests like "make a release", "prepare 1.0.0", "validate release artifacts", "cut a tag", or "publish to PyPI".

## Release Posture

Treat releases as packaging and API stabilization work, not opportunistic refactors. Keep edits scoped to release correctness: public API contracts, version metadata, changelog, docs, quality gates, artifacts, and publish automation.

Before changing files, read the latest release plan if one exists under `docs/superpowers/plans/*release*.md`. If the plan has task checkboxes, keep progress updated there so another agent can resume.

## Workflow

1. Start from a clean, synchronized `main` unless the user explicitly names another branch.
2. Preserve any existing user work before switching branches. Do not overwrite dirty or untracked files.
3. Create a release branch, normally `release/vX.Y.Z`.
4. Update package metadata and supported Python classifiers consistently across `pyproject.toml`, `src/quantik_core/__init__.py`, docs, and changelog.
5. Review the public API surface and import cost. Stable exports belong in `quantik_core.__init__`; experimental or heavy modules should stay explicit subpackage imports.
6. Update release documentation: `CHANGELOG.md`, `README.md`, architecture/API stability docs, examples, and any workflow notes affected by the release.
7. Verify artifacts before publishing: build sdist/wheel, inspect metadata, and run `twine check` when available.
8. Open a PR for review unless the user explicitly asks for a local-only release preparation.
9. After approval and green checks, tag from the merge commit and publish through the configured trusted release path.

## Required Local Gates

Use the repository virtual environment:

```bash
.venv/bin/python -m pytest tests/ -q --cov=quantik_core --cov-report=term-missing
.venv/bin/python -m black --check .
.venv/bin/python -m flake8 . --count --statistics
.venv/bin/python -m mypy src/quantik_core/
./auto-lint.sh
./dev-check.sh
```

If dependencies are missing, report the exact blocker and do not claim release readiness. Network-dependent installs or publishing require explicit permission.

## PR and Handoff

A release PR should include:

- release version and target tag
- notable API or packaging changes
- docs/changelog updates
- local gate results
- artifact validation status
- any publish blockers or manual steps

Do not publish, tag, or delete release branches unless the user has explicitly asked for that step.
