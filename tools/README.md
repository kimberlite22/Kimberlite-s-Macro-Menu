# codex-delegate.mjs

`codex-delegate.mjs` delegates a task to Codex, streams its reasoning to a Markdown file, and prints the final answer.

After a workspace-write delegation, it automatically reviews the changed files with the next model tier (`luna` -> `terra`, `terra` -> `sol`).

Options:

- `--model <name>`: Select the Codex model; otherwise use the global default.
- `--effort <level>`: Set reasoning effort to `none`, `minimal`, `low`, `medium`, `high`, or `xhigh`.
- `--sandbox <mode>`: Select the Codex sandbox; defaults to `workspace-write`.
- `--read-only`: Convenience alias for `--sandbox read-only`.
- `--reasoning-file <path>`: Choose the file receiving the live reasoning transcript.
- `--open`: Automatically open the reasoning file in its own VS Code tab (off by default).
- `--no-review`: Skip the automatic review after a workspace-write delegation.
- `--review-effort <level>`: Set the reasoning effort for the automatic review.

Example:

```powershell
node tools/codex-delegate.mjs --model gpt-5.6-luna --effort medium "Review the authentication flow"
```

For the full Codex delegation workflow, see [CLAUDE.md](../CLAUDE.md).
