#!/usr/bin/env node
// Regenerate tasklist/OVERVIEW.md from tasklist/open/ and tasklist/done/, so the file's own
// "AUTO-GENERATED, do not hand-edit" claim (see "Regenerating OVERVIEW.md" in CLAUDE.md) holds
// literally instead of relying on someone renumbering a group by hand after every task.
//
// Usage:
//   node tools/regen-overview.mjs           write tasklist/OVERVIEW.md
//   node tools/regen-overview.mjs --check   exit 1 if the file is stale, write nothing
//
// An open task file's Goal field is rendered as-is, word-wrapped, rather than hand-paraphrased
// down to "a few words": that keeps the file mechanically reproducible, which is the point, at
// the cost of being a little more verbose than a human summary would be. A done file's Result
// field is rendered as a single unwrapped line, per the task file format's own "Result: <one-
// line result>" template.

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const TASKLIST_DIR = path.join(REPO_ROOT, "tasklist");
const OVERVIEW_PATH = path.join(TASKLIST_DIR, "OVERVIEW.md");
const WRAP_WIDTH = 96;

// Fixed group order, matching the layout CLAUDE.md's "Tasklist routine" mandates.
const GROUPS = [
  { key: "fixes", heading: "FIXES" },
  { key: "workflow", heading: "WORKFLOW" },
  { key: "gui-ux", heading: "GUI & UX" },
  { key: "major", heading: "MAJOR" },
];

const OPEN_FIELDS = new Set(["Title", "Prio", "Goal", "Files", "Steps", "Open"]);
const DONE_FIELDS = new Set(["Title", "Completed", "Commit", "Result"]);
const FIELD_RE = /^([A-Za-z]+):\s?(.*)$/;

// A task file's fields can span several lines; anything that is not itself a recognized
// "Label:" line continues the field above it (see the task file format in CLAUDE.md).
function parseFields(text, knownLabels) {
  const chunks = {};
  let current = null;
  for (const rawLine of text.split(/\r?\n/)) {
    const match = rawLine.match(FIELD_RE);
    const label = match ? match[1] : null;
    if (label && knownLabels.has(label)) {
      current = label;
      chunks[current] = match[2].trim() ? [match[2].trim()] : [];
    } else if (current) {
      const trimmed = rawLine.trim();
      if (trimmed) chunks[current].push(trimmed);
    }
  }
  const fields = {};
  for (const [key, value] of Object.entries(chunks)) fields[key] = joinChunks(value);
  return fields;
}

// A source file's own hand-wrapping sometimes breaks a hyphenated or slash-joined compound
// (e.g. "window-\nclose", "presets/\nmap profiles") right at the line break, with no space on
// either side of the break in the intended text. Joining every continuation line with a plain
// space would turn those back into "window- close" / "presets/ map profiles". Detect that case
// (previous chunk ends with "-" or "/") and join those two chunks directly instead.
function joinChunks(chunks) {
  let out = "";
  for (const chunk of chunks) {
    if (out === "" || /[-/]$/.test(out)) out += chunk;
    else out += ` ${chunk}`;
  }
  return out;
}

function readTasks(dir, knownLabels) {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((name) => name.endsWith(".md"))
    .map((name) => ({
      slug: path.basename(name, ".md"),
      path: path.join(dir, name),
      fields: parseFields(fs.readFileSync(path.join(dir, name), "utf8"), knownLabels),
    }));
}

// Word-wraps `text` after `prefix`, continuing at `indent` on following lines. Never breaks a
// bare prefix/indent (with no word appended yet) even if that single word overruns the width,
// so one long slug or URL cannot produce an empty continuation line.
function wrap(prefix, text, indent) {
  const words = text.split(/\s+/).filter(Boolean);
  const lines = [];
  let line = prefix;
  for (const word of words) {
    const bare = line === prefix || line === indent;
    const sep = line.endsWith(" ") ? "" : " ";
    const candidate = `${line}${sep}${word}`;
    if (!bare && candidate.length > WRAP_WIDTH) {
      lines.push(line);
      line = `${indent}${word}`;
    } else {
      line = candidate;
    }
  }
  lines.push(line);
  return lines;
}

function renderOpenGroupLines(group) {
  const dir = path.join(TASKLIST_DIR, "open", group.key);
  const tasks = readTasks(dir, OPEN_FIELDS);
  const lines = [`## ${group.heading}`, ""];
  if (tasks.length === 0) {
    lines.push("(none open)");
    return lines;
  }

  tasks.sort((a, b) => {
    const prioA = Number(a.fields.Prio ?? Number.MAX_SAFE_INTEGER);
    const prioB = Number(b.fields.Prio ?? Number.MAX_SAFE_INTEGER);
    if (prioA !== prioB) return prioA - prioB;
    return a.slug.localeCompare(b.slug);
  });

  const seenPrio = new Map();
  tasks.forEach((task, index) => {
    const n = index + 1;
    const marker = `${n}. `;
    const prefix = `${marker}[${task.slug}](open/${group.key}/${task.slug}.md) - `;
    const indent = " ".repeat(marker.length);
    const goal = task.fields.Goal || task.fields.Title || "";
    lines.push(...wrap(prefix, goal, indent));
    if (index < tasks.length - 1) lines.push("");

    const prio = task.fields.Prio;
    if (prio !== undefined) {
      if (seenPrio.has(prio)) {
        process.stderr.write(
          `warning: duplicate Prio ${prio} in open/${group.key}: ${seenPrio.get(prio)} and ${task.slug}\n`,
        );
      }
      seenPrio.set(prio, task.slug);
    }
  });
  return lines;
}

function gitTimestamp(filePath) {
  try {
    const out = execFileSync("git", ["log", "-1", "--format=%ct", "--", filePath], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    }).trim();
    return out ? Number(out) : 0;
  } catch {
    return 0;
  }
}

function renderDoneLines() {
  const dir = path.join(TASKLIST_DIR, "done");
  const tasks = readTasks(dir, DONE_FIELDS);
  for (const task of tasks) task.timestamp = gitTimestamp(task.path);

  // Newest first: Completed date descending, each file's own last commit timestamp as the
  // tie-break for same-date entries (so same-day order stays the real chronological one instead
  // of an arbitrary alphabetical fallback), then slug as a final deterministic tie-break for
  // files completed in the very same commit, which share the same timestamp too.
  tasks.sort((a, b) => {
    const dateA = a.fields.Completed || "";
    const dateB = b.fields.Completed || "";
    if (dateA !== dateB) return dateA < dateB ? 1 : -1;
    if (a.timestamp !== b.timestamp) return b.timestamp - a.timestamp;
    return a.slug.localeCompare(b.slug);
  });

  const lines = ["## DONE (newest first)", ""];
  tasks.forEach((task, index) => {
    const date = task.fields.Completed || "????-??-??";
    const commit = task.fields.Commit || "-";
    const result = task.fields.Result || task.fields.Title || "";
    lines.push(`- ${date} [${task.slug}](done/${task.slug}.md) - ${result} (commit ${commit})`);
    if (index < tasks.length - 1) lines.push("");
  });
  return lines;
}

function render(today) {
  const headerLines = [
    "AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/open/ and tasklist/done/ instead",
    '(see "Tasklist routine" in CLAUDE.md). Run `node tools/regen-overview.mjs` after any change',
    "under tasklist/open/ or tasklist/done/ instead of editing this file by hand.",
    "",
    `Last regenerated: ${today}`,
  ];

  const parts = [headerLines, ...GROUPS.map(renderOpenGroupLines), renderDoneLines()];
  const outLines = [];
  parts.forEach((part, index) => {
    outLines.push(...part);
    if (index < parts.length - 1) outLines.push("");
  });
  return `${outLines.join("\n")}\n`;
}

// The "Last regenerated" date is the only line that legitimately changes on every run with no
// other content changed; strip it before diffing so --check does not flag pure date drift.
function withoutRegenDate(text) {
  return text.replace(/^Last regenerated: .*$/m, "Last regenerated: -");
}

function main() {
  const checkOnly = process.argv.includes("--check");
  const today = new Date().toISOString().slice(0, 10);
  const output = render(today);
  const current = fs.existsSync(OVERVIEW_PATH) ? fs.readFileSync(OVERVIEW_PATH, "utf8") : "";

  if (checkOnly) {
    if (withoutRegenDate(current) !== withoutRegenDate(output)) {
      process.stderr.write("tasklist/OVERVIEW.md is stale, run: node tools/regen-overview.mjs\n");
      process.exit(1);
    }
    process.stdout.write("tasklist/OVERVIEW.md is up to date.\n");
    return;
  }

  fs.writeFileSync(OVERVIEW_PATH, output);
  process.stdout.write(
    withoutRegenDate(current) === withoutRegenDate(output)
      ? "tasklist/OVERVIEW.md already up to date (date stamp refreshed).\n"
      : "tasklist/OVERVIEW.md regenerated.\n",
  );
}

main();
