#!/usr/bin/env node
// Delegate a coding subtask to Codex via `codex exec --json`, then (for a
// workspace-write run) AUTO-REVIEW the change with the next model tier up.
//
// Pipeline (one invocation does all of it):
//   1. Snapshot the working tree by file content hash.
//   2. Run the delegation (Codex implements the change).
//   3. Re-hash to find exactly which files were added / modified / removed
//      (content-based, so it is correct even when the tree was already dirty).
//   4. Review those files (read-only) with the reviewer one tier ABOVE the
//      implementer: luna -> terra, terra -> sol, else -> sol.
//   5. Print the delegation answer AND the review findings together.
//
// Each Codex run streams its reasoning LIVE into a per-model Markdown file in the
// repo root (codex-reasoning-<model>.md), appended per run. Not opened in VS Code
// unless --open is passed.
//
// Usage:
//   node tools/codex-delegate.mjs [--model <m>] [--effort <e>] [--read-only] \
//        [--review-effort <e>] [--no-review] [--reasoning-file <path>] [--open] "<task>"
//     --read-only     investigation/manual review; no file changes and no auto-review.
//     --no-review     skip the auto-review after a workspace-write delegation.
//     --review-effort effort for the auto-review (defaults to --effort).
//     --open          open each reasoning file in its own VS Code tab (off by default).
//   The task may be the trailing argument(s) or piped on stdin.

import { spawn, execSync, execFileSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

const EFFORTS = new Set(["none", "minimal", "low", "medium", "high", "xhigh"]);
const SANDBOXES = new Set(["read-only", "workspace-write", "danger-full-access"]);
const MODEL_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

// Suppress Node's DEP0190 "shell option" DeprecationWarning. shell:true is used
// deliberately to launch the Windows `codex`/`code` shims; every value that
// reaches the shell is validated against the whitelists above (see main()).
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

// The reviewer is one tier ABOVE the implementer.
export function reviewerFor(model) {
  const map = { luna: "gpt-5.6-terra", terra: "gpt-5.6-sol", sol: "gpt-5.6-sol" };
  return map[modelLabel(model)] || "gpt-5.6-sol";
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
    let holder = 0;
    try { holder = parseInt(fs.readFileSync(lockPath, "utf8").trim(), 10) || 0; } catch { /* ignore */ }
    if (holder && !pidAlive(holder)) {
      try { fs.writeFileSync(lockPath, String(process.pid)); return { file: preferred, lockPath }; } catch { /* ignore */ }
    }
    return { file: path.join(os.tmpdir(), `codex-reasoning-${label}-${process.pid}.md`), lockPath: null };
  }
}

// process.env with `safe.directory=*` APPENDED (not clobbering any caller-provided
// GIT_CONFIG_* entries) so git works despite the Codex sandbox "dubious ownership".
function gitEnv() {
  const env = { ...process.env };
  const n = parseInt(env.GIT_CONFIG_COUNT || "0", 10) || 0;
  env.GIT_CONFIG_COUNT = String(n + 1);
  env[`GIT_CONFIG_KEY_${n}`] = "safe.directory";
  env[`GIT_CONFIG_VALUE_${n}`] = "*";
  return env;
}

// NUL-separated `git` output as an array (path-safe, no porcelain parsing).
// Returns null on failure (distinct from an empty list).
function gitListZ(args) {
  try {
    const out = execSync(`git ${args}`, { cwd: REPO_ROOT, encoding: "utf8", env: gitEnv(), maxBuffer: 256 * 1024 * 1024 });
    return out.split("\0").filter(Boolean);
  } catch {
    return null;
  }
}

// All non-ignored files (tracked + untracked). null on git failure.
function candidateFiles() {
  const tracked = gitListZ("ls-files -z");
  const untracked = gitListZ("ls-files --others --exclude-standard -z");
  if (tracked === null || untracked === null) return null;
  return [...new Set([...tracked, ...untracked])];
}

// Snapshot of the working tree: per-file content hash (for change detection) and
// the file content itself (so we can later diff ONLY the delegation's own changes,
// even inside a file that was already dirty). Returns { hashes, content } or null
// on git failure.
function snapshotTree() {
  const files = candidateFiles();
  if (files === null) return null;
  const hashes = new Map();
  const content = new Map();
  for (const f of files) {
    try {
      const buf = fs.readFileSync(path.join(REPO_ROOT, f));
      content.set(f, buf);
      hashes.set(f, crypto.createHash("sha1").update(buf).digest("hex"));
    } catch {
      content.set(f, null);
      hashes.set(f, "MISSING");
    }
  }
  return { hashes, content };
}

// Unified diff of ONLY the delegation's changes (pre-delegation content vs the
// current file) for each changed path, isolated from any pre-existing uncommitted
// edits. Uses `git diff --no-index` between a temp "before" file and the live file.
export function isolatedDiff(changed, beforeContent) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "codex-iso-"));
  const parts = [];
  try {
    for (const f of changed) {
      const beforeBuf = beforeContent.get(f) ?? Buffer.alloc(0); // absent -> file is new
      const beforePath = path.join(tmp, "before");
      fs.writeFileSync(beforePath, beforeBuf ?? Buffer.alloc(0));
      const realPath = path.join(REPO_ROOT, f);
      let afterPath = realPath;
      if (!fs.existsSync(realPath)) { afterPath = path.join(tmp, "after"); fs.writeFileSync(afterPath, Buffer.alloc(0)); }
      let d = "";
      try {
        d = execFileSync("git", ["-c", "core.autocrlf=false", "diff", "--no-index", "--no-color", "--", beforePath, afterPath],
          { cwd: REPO_ROOT, encoding: "utf8", env: gitEnv(), maxBuffer: 64 * 1024 * 1024 });
      } catch (e) {
        d = (e.stdout || "").toString(); // git diff --no-index exits 1 when files differ
      }
      parts.push(relabelDiff(d, f).trim() || `### ${f}: content changed (no textual diff; possibly binary)`);
    }
  } finally {
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
  }
  return parts.join("\n");
}

// Rewrite git's diff header lines (which carry the absolute temp paths) to the
// real repo-relative path, so the reviewer sees `a/<f>` / `b/<f>` and never the
// temp scaffolding. Robust regardless of how git formatted the given paths.
function relabelDiff(diffText, f) {
  // Only the pre-hunk header carries the temp paths. Never touch hunk body lines:
  // a removed line "-- x" prints as "--- x" and an added "++ x" as "+++ x".
  let inHeader = true;
  return diffText.split("\n").map((line) => {
    if (inHeader) {
      if (line.startsWith("@@")) { inHeader = false; return line; }
      if (line.startsWith("diff --git ")) return `diff --git a/${f} b/${f}`;
      if (line.startsWith("--- ")) return line.includes("/dev/null") ? line : `--- a/${f}`;
      if (line.startsWith("+++ ")) return line.includes("/dev/null") ? line : `+++ b/${f}`;
    }
    return line;
  }).join("\n");
}

// Files whose content differs between two snapshots (added / modified / removed).
// Pure and exported for testing.
export function changedFiles(before, after) {
  const changed = new Set();
  for (const [f, h] of after) if (before.get(f) !== h) changed.add(f);
  for (const f of before.keys()) if (!after.has(f)) changed.add(f);
  return [...changed];
}

function parseArgs(argv) {
  const opts = {
    model: null, effort: null, sandbox: "workspace-write",
    reasoningFile: null, openInVscode: false, noReview: false, reviewEffort: null,
  };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--model") opts.model = argv[++i];
    else if (a === "--effort") opts.effort = argv[++i];
    else if (a === "--review-effort") opts.reviewEffort = argv[++i];
    else if (a === "--read-only") opts.sandbox = "read-only";
    else if (a === "--sandbox") opts.sandbox = argv[++i];
    else if (a === "--no-review") opts.noReview = true;
    else if (a === "--reasoning-file") opts.reasoningFile = argv[++i];
    else if (a === "--open") opts.openInVscode = true;
    else if (a === "--no-open") opts.openInVscode = false; // kept for compatibility; this is now the default
    else rest.push(a);
  }
  opts.task = rest.join(" ").trim();
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
  return String(text).replace(/\*\*/g, "").replace(/\s+/g, " ").trim();
}

function shortCommand(cmd) {
  return String(cmd).replace(/\s+/g, " ").trim().slice(0, 100);
}

// Run one Codex `exec --json` session, streaming its reasoning live into a
// per-model reasoning file (opened in its own VS Code tab only if openInVscode).
// Resolves with { answer, exitCode, reasoningFile, commandsRun, commandsFailed }.
function runCodexSession({ model, effort, sandbox, task, openInVscode, reasoningFileOverride }) {
  return new Promise((resolve) => {
    const label = modelLabel(model);
    const preferred = reasoningFileOverride || path.join(REPO_ROOT, `codex-reasoning-${label}.md`);
    const { file: reasoningFile, lockPath } = acquireReasoningFile(preferred, label);
    let released = false;
    const releaseLock = () => { if (!released && lockPath) { released = true; try { fs.unlinkSync(lockPath); } catch { /* ignore */ } } };
    process.once("exit", releaseLock);

    const started = new Date().toISOString();
    const append = (line) => { try { fs.appendFileSync(reasoningFile, line, "utf8"); } catch { /* ignore */ } };
    const isNew = !fs.existsSync(reasoningFile) || fs.statSync(reasoningFile).size === 0;
    append(
      `${isNew ? "" : "\n\n"}${"=".repeat(70)}\n# Codex run - ${started}\n\n` +
      `- Model: ${model ?? "global default"}\n- Sandbox: ${sandbox}\n` +
      `- Task: ${task.replace(/\s+/g, " ").trim().slice(0, 600)}\n\n## Thought process\n\n`
    );

    let tabOpened = false;
    const openReasoningTab = () => {
      if (tabOpened || !openInVscode) return;
      tabOpened = true;
      // Quote the path so spaces survive the shell; the path is validated to
      // contain no double-quote/newline in main().
      try { spawn("code", ["-r", `"${reasoningFile}"`], { shell: true, stdio: "ignore", detached: true }).unref(); } catch { /* ignore */ }
    };

    const messages = [];
    let commandsRun = 0, commandsFailed = 0, stderr = "", buf = "";
    const handleLine = (line) => {
      if (!line.trim()) return;
      let o;
      try { o = JSON.parse(line); } catch { return; }
      if (o.type !== "item.completed" || !o.item) return;
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
    };

    let settled = false;
    const finish = (code) => {
      if (settled) return;
      settled = true;
      if (buf.trim()) { handleLine(buf); buf = ""; } // trailing record without a newline
      const answer = messages.length ? messages[messages.length - 1] : "(Codex returned no final message.)";
      append(`\n## Answer\n\n${answer}\n\n- Completed: ${new Date().toISOString()}\n`);
      if (code !== 0 && stderr.trim()) append(`\n## Error (exit ${code})\n\n\`\`\`text\n${stderr.trim()}\n\`\`\`\n`);
      openReasoningTab();
      releaseLock();
      resolve({ answer, exitCode: code, reasoningFile, commandsRun, commandsFailed });
    };

    const args = ["exec", "--json", "-s", sandbox];
    if (model) args.push("-m", model);
    if (effort) args.push("-c", `model_reasoning_effort=${effort}`);

    const child = spawn("codex", args, { shell: true, stdio: ["pipe", "pipe", "pipe"] });
    child.on("error", (err) => { stderr += `spawn error: ${err.message}\n`; finish(1); });
    child.stdin.on("error", () => { /* ignore EPIPE if the child never started */ });
    try { child.stdin.write(task); child.stdin.end(); } catch { /* ignore */ }

    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.stdout.on("data", (d) => {
      buf += d.toString();
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl);
        buf = buf.slice(nl + 1);
        handleLine(line);
      }
    });
    child.on("close", (code) => finish(code === null ? 1 : code));
  });
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const task = opts.task || (await readStdin());
  if (!task) {
    console.error('usage: node tools/codex-delegate.mjs [--model M] [--effort E] [--read-only] [--no-review] "<task>"');
    process.exit(2);
  }

  // Validate every value that reaches a shell (shell:true) or a review sub-shell.
  const bad = (m) => { console.error(m); process.exit(2); };
  if (opts.model && !MODEL_RE.test(opts.model)) bad(`invalid --model: ${opts.model}`);
  if (opts.effort && !EFFORTS.has(opts.effort)) bad(`invalid --effort: ${opts.effort}`);
  if (opts.reviewEffort && !EFFORTS.has(opts.reviewEffort)) bad(`invalid --review-effort: ${opts.reviewEffort}`);
  if (!SANDBOXES.has(opts.sandbox)) bad(`invalid --sandbox: ${opts.sandbox}`);
  if (opts.reasoningFile && /["\n\r]/.test(opts.reasoningFile)) bad(`invalid --reasoning-file: ${opts.reasoningFile}`);

  // Content snapshot BEFORE the delegation so we can detect exactly what it
  // changed, even if the tree was already dirty.
  const willReview = opts.sandbox !== "read-only" && !opts.noReview;
  const before = willReview ? snapshotTree() : null;

  const delegation = await runCodexSession({
    model: opts.model, effort: opts.effort, sandbox: opts.sandbox, task,
    openInVscode: opts.openInVscode, reasoningFileOverride: opts.reasoningFile,
  });

  let review = null, changed = [], detectFailed = false;
  if (willReview) {
    const after = snapshotTree();
    if (before === null || after === null) {
      detectFailed = true;
    } else {
      changed = changedFiles(before.hashes, after.hashes);
      if (changed.length) {
        const reviewer = reviewerFor(opts.model);
        const diff = isolatedDiff(changed, before.content);
        const reviewTask =
          `You are a code reviewer. The fenced diff below is EXACTLY and ONLY what the delegation just changed, ` +
          `isolated from any pre-existing uncommitted edits in these files. Review only these changes; do NOT ` +
          `re-report unrelated pre-existing code. Report issues with file:line; if none, say it looks good. ` +
          `Do not modify any files.\n\n` +
          "```diff\n" + diff + "\n```\n\n" +
          `For additional context you may read the current file(s): ${changed.join(", ")}.`;
        review = await runCodexSession({
          model: reviewer, effort: opts.reviewEffort || opts.effort, sandbox: "read-only",
          task: reviewTask, openInVscode: opts.openInVscode,
        });
        review.reviewer = reviewer;
      }
    }
  }

  const out = [`## Delegation (${modelLabel(opts.model)})`, "", delegation.answer, ""];
  if (delegation.commandsRun) out.push(`Ran ${delegation.commandsRun} shell command(s)${delegation.commandsFailed ? `, ${delegation.commandsFailed} failed` : ""}.`);
  out.push(`Reasoning: ${delegation.reasoningFile}`);
  if (review) {
    out.push("", "---", "", `## Auto-review (${modelLabel(review.reviewer)}) of: ${changed.join(", ")}`, "", review.answer, "");
    out.push(`Reasoning: ${review.reasoningFile}`);
  } else if (detectFailed) {
    out.push("", "> Could not determine changed files (git snapshot failed) -> auto-review skipped; review manually.");
  } else if (willReview) {
    out.push("", "(No file changes detected -> no auto-review.)");
  } else if (opts.noReview) {
    out.push("", "(--no-review: auto-review skipped.)");
  }

  // Reflect BOTH the delegation and the review (and detection failure) in the exit
  // code so automation can tell when the required review did not succeed.
  process.exitCode = delegation.exitCode || (review ? review.exitCode : 0) || (detectFailed ? 1 : 0);
  process.stdout.write(out.join("\n") + "\n");
}

// Run only when invoked directly (not when imported for testing).
if (import.meta.url === pathToFileURL(process.argv[1] || "").href) main();
