# codex-delegate.mjs

`codex-delegate.mjs` delegates a task to Codex, streams its reasoning to a Markdown file, and prints the final answer.

Options:

- `--model <name>`: Select the Codex model; otherwise use the global default.
- `--effort <level>`: Set reasoning effort to `none`, `minimal`, `low`, `medium`, `high`, or `xhigh`.
- `--sandbox <mode>`: Select the Codex sandbox; defaults to `workspace-write`.
- `--read-only`: Convenience alias for `--sandbox read-only`.
- `--reasoning-file <path>`: Choose the file receiving the live reasoning transcript.
- `--no-open`: Do not automatically open the reasoning file in VS Code.

Example:

```powershell
node tools/codex-delegate.mjs --model gpt-5.6-luna --effort medium "Review the authentication flow"
```
