
After receiving a clear definition of goal, use a superior model (`opus`, `fable`) as a consultant and coordinator, while coding tasks implementation can be delegated to `sonnet`/`haiku`. 

Use an agent team where you have a team lead, teammates (sub-agents) who share the same tasklist and can communicate over a messaging system (mailbox).

Be mindful about token consumption and which model needs to be used.

### Guardrails around code quality

Every new feature, contract adapter, CLI entry point, parser, exporter, or bug
fix must include focused unit tests for the new behavior. Do not rely only on an
end-to-end smoke test or CI workflow. Add direct tests for success cases,
validation/error cases, and any compatibility fallback introduced by the change.
Before opening or updating a PR, explicitly check that the relevant unit tests
exist and mention them in the PR validation notes.

Local development using .venv
```
# Check if .venv folder exists
if [ ! -d ".venv" ]; then
    # Create virtual environment
    python -m venv .venv

    # Install development dependencies
    .venv/bin/python -m pip install -e ".[dev,cbor]"
fi

PYTHON=".venv/bin/python"
```

Pre-commit checks:
1. Auto-fix lint: `./auto-lint.sh`
2. Full CI checks: `./dev-check.sh`

## Agentic Release Work

For release tasks, use the Claude skill at `.claude/skills/make-release/SKILL.md`. Keep release work scoped, preserve user changes before branch operations, use `.venv`, run `./auto-lint.sh` before commits, and run `./dev-check.sh` before pushes or release handoff.
