#!/usr/bin/env node
// Delegate a coding subtask to Codex via `codex exec --json` (or run a review with
// --read-only). Codex's reasoning ("thought process") is streamed LIVE, line by
// line, into a per-model Markdown file in the repo root and auto-opened in VS Code.
//
// Behaviour:
//   - Per-model file:   codex-reasoning-<model>.md (e.g. ...-luna.md, ...-sol.md).
//   - Append, never wipe: each run appends a new dated section; previous thought
//     processes are kept. To clear the history, delete the file yourself.
//   - Concurrency-safe: if the per-model file is already held by another running
//     instance, this run streams to a separate temp file instead, so simultaneous
//     runs never interleave. That temp file is opened in VS Code too.
//   - Only the final answer (plus the reasoning-file path) is printed to stdout,
//     keeping the reasoning out of the caller's chat.
//
// Usage:
//   node tools/codex-delegate.mjs [--model <m>] [--effort <e>] [--read-only] \
//        [--reasoning-file <path>] [--no-open] "<task>"
//   The task may be the trailing argument(s) or piped on stdin.

import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

// Suppress Node's DEP0190 "shell option" DeprecationWarning (shell:true is used
// deliberately to launch the Windows `codex`/`code` shims).
const _emitWarning = process.emitWarning.bind(process);
process.emitWarning = (warning, ...rest) => {
  const name = typeof warning === "object" && warning ? warning.name : rest[0]?.type ?? rest[0];
  if (name === "DeprecationWarning") return;
  return _emitWarning(warning, ...rest);
};

// Short, filesystem-safe label for a model (e.g. "gpt-5.6-luna" -> "luna").
export function modelLabel(model) {
  if (!model) return "default";
  const trailing = model.match(/([a-z0-9]+)\s*$/i);
  return (trailing ? trailing[1] : model).replace(/[^a-z0-9]+/gi, "-").toLowerCase();
}

function pidAlive(pid) {
  try { process.kill(pid, 0); return true; } catch (e) { return e.code === "EPERM"; }
}

// Choose the reasoning file to write to. Prefer `preferred`; if another live
// instance already holds its lock, fall back to a unique temp file so concurrent
// runs never interleave. Returns { file, lockPath } (lockPath null when unlocked).
export function acquireReasoningFile(preferred, label) {
  const lockPath = `${preferred}.lock`;
  try {
    const fd = fs.openSync(lockPath, "wx"); // exclusive create
    fs.writeSync(fd, String(process.pid));
    fs.closeSync(fd);
    return { file: preferred, lockPath };
  } catch (e) {
    if (e.code !== "EEXIST") return { file: preferred, lockPath: null };
    // Lock exists: reclaim it only if the holder is a known, dead process.
    let holder = 0;
    try { holder = parseInt(fs.readFileSync(lockPath, "utf8").trim(), 10) || 0; } catch { /* ignore */ }
    if (holder && !pidAlive(holder)) {
      try { fs.writeFileSync(lockPath, String(process.pid)); return { file: preferred, lockPath }; } catch { /* ignore */ }
    }
    // A live (or unknown) instance holds it: stream to a separate temp file.
    return { file: path.join(os.tmpdir(), `codex-reasoning-${label}-${process.pid}.md`), lockPath: null };
  }
}

function parseArgs(argv) {
  const opts = { model: null, effort: null, sandbox: "workspace-write", reasoningFile: null, openInVscode: true };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--model") opts.model = argv[++i];
    else if (a === "--effort") opts.effort = argv[++i];
    else if (a === "--read-only") opts.sandbox = "read-only";
    else if (a === "--sandbox") opts.sandbox = argv[++i];
    else if (a === "--reasoning-file") opts.reasoningFile = argv[++i];
    else if (a === "--no-open") opts.openInVscode = false;
    else rest.push(a);
  }
  opts.task = rest.join(" ").trim();
  if (!opts.reasoningFile) opts.reasoningFile = path.join(REPO_ROOT, `codex-reasoning-${modelLabel(opts.model)}.md`);
  return opts;
}

function readStdin() {
  return new Promise((resolve) => {
    if (process.stdin.isTTY) return resolve("");
    let s = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (d) => (s += d));
    process.stdin.on("end", () => resolve(s.trim()));
    process.stdin.on("error", () => resolve(s.trim()));
  });
}

function cleanReasoning(text) {
  // Codex reasoning summaries arrive as short bold headers like "**Doing X**".
  return String(text).replace(/\*\*/g, "").replace(/\s+/g, " ").trim();
}

function shortCommand(cmd) {
  return String(cmd).replace(/\s+/g, " ").trim().slice(0, 100);
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const task = opts.task || (await readStdin());
  if (!task) {
    console.error('usage: node tools/codex-delegate.mjs [--model M] [--effort E] [--read-only] "<task>"');
    process.exit(2);
  }

  const label = modelLabel(opts.model);
  const { file: reasoningFile, lockPath } = acquireReasoningFile(opts.reasoningFile, label);
  const releaseLock = () => { if (lockPath) { try { fs.unlinkSync(lockPath); } catch { /* ignore */ } } };
  process.on("exit", releaseLock);

  const started = new Date().toISOString();
  const append = (line) => { try { fs.appendFileSync(reasoningFile, line, "utf8"); } catch { /* ignore */ } };

  // Append a new run section (never truncate; previous thought processes are kept).
  const isNew = !fs.existsSync(reasoningFile) || fs.statSync(reasoningFile).size === 0;
  append(
    `${isNew ? "" : "\n\n"}${"=".repeat(70)}\n# Codex run - ${started}\n\n` +
    `- Model: ${opts.model ?? "global default"}\n- Sandbox: ${opts.sandbox}\n` +
    `- Task: ${task.replace(/\s+/g, " ").trim()}\n\n## Thought process\n\n`
  );

  // Open THIS reasoning file in VS Code the first time it receives a thought-process
  // update (idempotent per run; `code -r` opens the tab if it is not already open, or
  // just focuses it if it is). Each per-model file opens independently. Best-effort.
  let tabOpened = false;
  const openReasoningTab = () => {
    if (tabOpened || !opts.openInVscode) return;
    tabOpened = true;
    try { spawn("code", ["-r", reasoningFile], { shell: true, stdio: "ignore", detached: true }).unref(); } catch { /* ignore */ }
  };

  const args = ["exec", "--json", "-s", opts.sandbox];
  if (opts.model) args.push("-m", opts.model);
  if (opts.effort) args.push("-c", `model_reasoning_effort=${opts.effort}`);

  // Task on stdin (prompt read from stdin when omitted as an arg) avoids all
  // shell-quoting problems with the task text.
  const child = spawn("codex", args, { shell: true, stdio: ["pipe", "pipe", "pipe"] });
  child.stdin.write(task);
  child.stdin.end();

  const messages = [];
  let commandsRun = 0;
  let commandsFailed = 0;
  let stderr = "";
  let buf = "";

  child.stderr.on("data", (d) => (stderr += d.toString()));
  child.stdout.on("data", (d) => {
    buf += d.toString();
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl);
      buf = buf.slice(nl + 1);
      if (!line.trim()) continue;
      let o;
      try { o = JSON.parse(line); } catch { continue; }
      if (o.type !== "item.completed" || !o.item) continue;
      const it = o.item;
      if (it.type === "reasoning" && it.text) { append(`- ${cleanReasoning(it.text)}\n`); openReasoningTab(); }
      else if (it.type === "agent_message" && it.text) messages.push(it.text.trim());
      else if (it.type === "command_execution") {
        commandsRun++;
        const failed = it.status === "failed" || (typeof it.exit_code === "number" && it.exit_code !== 0);
        if (failed) commandsFailed++;
        append(`  - ran: \`${shortCommand(it.command)}\`${failed ? " (failed)" : ""}\n`);
        openReasoningTab();
      }
    }
  });

  child.on("close", (code) => {
    const answer = messages.length ? messages[messages.length - 1] : "(Codex returned no final message.)";
    append(`\n## Answer\n\n${answer}\n\n- Completed: ${new Date().toISOString()}\n`);
    if (code !== 0 && stderr.trim()) append(`\n## Error (exit ${code})\n\n\`\`\`text\n${stderr.trim()}\n\`\`\`\n`);
    openReasoningTab(); // fallback: ensure the tab opens even if the run produced no reasoning
    releaseLock();

    const out = ["## Answer", "", answer, ""];
    if (commandsRun) out.push(`Ran ${commandsRun} shell command(s)${commandsFailed ? `, ${commandsFailed} failed` : ""}.`);
    out.push(`Full live reasoning: ${reasoningFile}`);
    if (code !== 0) out.push("", `> Codex exited with code ${code}. See the reasoning file for details.`);
    // Set exitCode instead of process.exit() so buffered stdout (a pipe when this
    // wrapper is called by another process) is fully flushed first.
    process.exitCode = code ?? 0;
    process.stdout.write(out.join("\n") + "\n");
  });
}

// Run only when invoked directly (not when imported for testing).
if (import.meta.url === pathToFileURL(process.argv[1] || "").href) main();
