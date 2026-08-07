#!/usr/bin/env node
// Regenerate tasklist/OVERVIEW.md (open tasks) and tasklist/DONE.md (the finished archive) from
// tasklist/open/ and tasklist/done/, so each file's own "AUTO-GENERATED, do not hand-edit" claim
// (see "Regenerating the indexes" in CLAUDE.md) holds literally instead of relying on someone
// renumbering a group by hand after every task. They are two files because the done archive was
// 89% of the old combined one and is never needed to pick or plan a task, so splitting it keeps
// the file agents actually read small.
//
// Usage:
//   node tools/regen-overview.mjs           write both files
//   node tools/regen-overview.mjs --check   exit 1 if either file is stale, write nothing
//
// An open task file's Goal field is capped mechanically and then word-wrapped, rather than hand-
// paraphrased down to "a few words". A done file's Result field is rendered as a single unwrapped
// line, per the task file format's own "Result: <one-line result>" template.

import fs from "node:fs";
import path from "node:path";
import {
  GROUPS,
  DONE_FIELDS,
  OPEN_FIELDS,
  TASKLIST_DIR,
  readTasks,
  sortDoneTasks,
  sortOpenTasks,
  gitTimestamp,
} from "./tasklist-lib.mjs";

const OVERVIEW_PATH = path.join(TASKLIST_DIR, "OVERVIEW.md");
const DONE_PATH = path.join(TASKLIST_DIR, "DONE.md");
const WRAP_WIDTH = 96;

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

  sortOpenTasks(tasks);

  const seenPrio = new Map();
  tasks.forEach((task, index) => {
    const n = index + 1;
    const marker = `${n}. `;
    const prefix = `${marker}[${task.slug}](open/${group.key}/${task.slug}.md) - `;
    const indent = " ".repeat(marker.length);
    const goal = truncateOpenGoal(task.fields.Goal || task.fields.Title || "", group.key, task.slug);
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

function renderDoneLines() {
  const dir = path.join(TASKLIST_DIR, "done");
  const tasks = readTasks(dir, DONE_FIELDS);
  for (const task of tasks) task.timestamp = gitTimestamp(task.path);

  // Newest first: Completed date descending, each file's own last commit timestamp as the
  // tie-break for same-date entries (so same-day order stays the real chronological one instead
  // of an arbitrary alphabetical fallback), then slug as a final deterministic tie-break for
  // files completed in the very same commit, which share the same timestamp too.
  sortDoneTasks(tasks);

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

// Caps the rendered Goal at 400 characters of task text, cut on a word boundary, plus a fixed
// pointer to the file holding the rest. The bound has to hold for ANY input, so a single word
// longer than the cap is hard-cut at it rather than passed through whole: the whole point of the
// cap is that one task's pasted investigation brief cannot dominate the index.
function truncateOpenGoal(goal, group, slug) {
  const limit = 400;
  if (goal.length <= limit) return goal;
  const cut = goal.slice(0, limit);
  const atBoundary = /\s/.test(goal[limit]) ? cut.trimEnd() : cut.replace(/\s+\S*$/, "");
  return `${atBoundary || cut} [...] (full text in open/${group}/${slug}.md)`;
}

function overviewHeader(today) {
  return [
    "AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/open/ and tasklist/done/ instead",
    '(see "Tasklist routine" in CLAUDE.md). Run `node tools/regen-overview.mjs` after any change',
    "under tasklist/open/ or tasklist/done/ instead of editing this file by hand.",
    "Finished-task archive: tasklist/DONE.md.",
    "",
    `Last regenerated: ${today}`,
  ];
}

function doneHeader(today) {
  return [
    "AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/done/ instead",
    '(see "Tasklist routine" in CLAUDE.md). Run `node tools/regen-overview.mjs` after any change',
    "under tasklist/done/ instead of editing this file by hand.",
    "",
    `Last regenerated: ${today}`,
  ];
}

function joinParts(parts) {
  const outLines = [];
  parts.forEach((part, index) => {
    outLines.push(...part);
    if (index < parts.length - 1) outLines.push("");
  });
  return `${outLines.join("\n")}\n`;
}

function renderOverview(today) {
  return joinParts([overviewHeader(today), ...GROUPS.map(renderOpenGroupLines)]);
}

function renderDone(today) {
  return joinParts([doneHeader(today), renderDoneLines()]);
}

// The "Last regenerated" date is the only line that legitimately changes on every run with no
// other content changed; strip it before diffing so --check does not flag pure date drift.
function withoutRegenDate(text) {
  return text.replace(/^Last regenerated: .*$/m, "Last regenerated: -");
}

function main() {
  const checkOnly = process.argv.includes("--check");
  const today = new Date().toISOString().slice(0, 10);
  const overviewOutput = renderOverview(today);
  const doneOutput = renderDone(today);
  const currentOverview = fs.existsSync(OVERVIEW_PATH) ? fs.readFileSync(OVERVIEW_PATH, "utf8") : "";
  const currentDone = fs.existsSync(DONE_PATH) ? fs.readFileSync(DONE_PATH, "utf8") : "";

  if (checkOnly) {
    const stale = [];
    if (withoutRegenDate(currentOverview) !== withoutRegenDate(overviewOutput)) stale.push("tasklist/OVERVIEW.md");
    if (withoutRegenDate(currentDone) !== withoutRegenDate(doneOutput)) stale.push("tasklist/DONE.md");
    if (stale.length > 0) {
      process.stderr.write(`${stale.join(" and ")} ${stale.length === 1 ? "is" : "are"} stale, run: node tools/regen-overview.mjs\n`);
      process.exit(1);
    }
    process.stdout.write("tasklist/OVERVIEW.md and tasklist/DONE.md are up to date.\n");
    return;
  }

  fs.writeFileSync(OVERVIEW_PATH, overviewOutput);
  fs.writeFileSync(DONE_PATH, doneOutput);
  process.stdout.write(
    withoutRegenDate(currentOverview) === withoutRegenDate(overviewOutput) &&
      withoutRegenDate(currentDone) === withoutRegenDate(doneOutput)
      ? "tasklist/OVERVIEW.md and tasklist/DONE.md already up to date (date stamps refreshed).\n"
      : "tasklist/OVERVIEW.md and tasklist/DONE.md regenerated.\n",
  );
}

main();
