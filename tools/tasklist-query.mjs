#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import {
  DONE_FIELDS,
  GROUPS,
  OPEN_FIELDS,
  TASKLIST_DIR,
  gitTimestamp,
  readTasks,
  sortDoneTasks,
  sortOpenTasks,
} from "./tasklist-lib.mjs";

const OPEN_DIR = path.join(TASKLIST_DIR, "open");
const DONE_DIR = path.join(TASKLIST_DIR, "done");
const SEARCH_DONE_FIELDS = new Set([...DONE_FIELDS, "Goal"]);

function relativeTaskPath(task) {
  return path.relative(TASKLIST_DIR, task.path).split(path.sep).join("/");
}

// Keeps at most `limit` characters of `text`, cut on a word boundary, then appends `suffix`. The
// bound has to hold for ANY input, so a single word longer than `limit` is hard-cut at it rather
// than passed through whole, which would defeat the cap this exists for.
function truncateAtWord(text, limit, suffix = " [...]") {
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  const atBoundary = /\s/.test(text[limit]) ? cut.trimEnd() : cut.replace(/\s+\S*$/, "");
  return `${atBoundary || cut}${suffix}`;
}

function openTasksForGroup(group) {
  return sortOpenTasks(readTasks(path.join(OPEN_DIR, group.key), OPEN_FIELDS));
}

function compactTaskLine(group, task) {
  const goal = task.fields.Goal || task.fields.Title || "";
  const prio = task.fields.Prio ?? "?";
  return `${group.key}/${task.slug} (P${prio}) - ${truncateAtWord(goal, 120)}`;
}

function listGroups(groups) {
  const lines = [];
  for (const group of groups) {
    const tasks = openTasksForGroup(group);
    lines.push(`${group.heading} (${tasks.length})`);
    lines.push(...tasks.map((task) => compactTaskLine(group, task)));
  }
  return lines;
}

// Goal is capped the same way the OVERVIEW index caps it: whoever runs this is about to read the
// task file itself for Files:/Steps:, so printing a multi-kilobyte Goal here just pays for the same
// text twice. Open: is printed in full instead, since it is short and is the thing that blocks a
// start, so it is worth having before deciding to open the file at all.
function next() {
  for (const group of GROUPS) {
    const task = openTasksForGroup(group)[0];
    if (!task) continue;
    const goal = task.fields.Goal || task.fields.Title || "";
    const lines = [
      `Group: ${group.key}`,
      `Prio: ${task.fields.Prio ?? "?"}`,
      `Slug: ${task.slug}`,
      `Path: ${relativeTaskPath(task)}`,
      `Goal: ${truncateAtWord(goal, 400)}`,
      `Open: ${task.fields.Open || ""}`,
    ];
    process.stdout.write(`${lines.join("\n")}\n`);
    return;
  }
  process.stdout.write("No open tasks found.\n");
}

// An open task carries its description in Goal, a finished one in Result (see the two task file
// formats in CLAUDE.md), so both fields have to be searched and displayed for a query to reach
// text that only ever existed in a completed task's one-line result.
function searchableText(task) {
  return [task.fields.Title, task.fields.Goal, task.fields.Result].filter(Boolean).join("\n");
}

function displayText(task) {
  return task.fields.Goal || task.fields.Result || task.fields.Title || "";
}

function find(text) {
  const needle = text.toLowerCase();
  const hits = [];
  for (const group of GROUPS) {
    for (const task of openTasksForGroup(group)) {
      const haystack = `${task.slug}\n${searchableText(task)}`.toLowerCase();
      if (haystack.includes(needle)) hits.push({ status: "OPEN", task });
    }
  }

  const doneTasks = readTasks(DONE_DIR, SEARCH_DONE_FIELDS);
  for (const task of doneTasks) task.timestamp = gitTimestamp(task.path);
  for (const task of sortDoneTasks(doneTasks)) {
    const haystack = `${task.slug}\n${searchableText(task)}`.toLowerCase();
    if (haystack.includes(needle)) hits.push({ status: "DONE", task });
  }

  for (const { status, task } of hits) {
    process.stdout.write(`${status} ${relativeTaskPath(task)} - ${truncateAtWord(displayText(task), 120)}\n`);
  }
  if (hits.length === 0) process.stdout.write(`No open or done task matches "${text}".\n`);
}

function reviews() {
  const reviewPath = path.join(TASKLIST_DIR, "PENDING_REVIEW.md");
  const text = fs.existsSync(reviewPath) ? fs.readFileSync(reviewPath, "utf8") : "";
  const groupStart = text.search(/^## /m);
  if (groupStart === -1) {
    process.stdout.write("0 of 0 entries have a filled-in Review: line\n");
    return;
  }

  const lines = text.slice(groupStart).split(/\r?\n/);
  const entries = [];
  let group = "";
  let current = null;
  for (const line of lines) {
    if (/^## /.test(line)) {
      if (current) entries.push(current);
      current = null;
      group = line.slice(3).trim();
      continue;
    }
    const match = line.match(/^- (\S+) - /);
    if (match) {
      if (current) entries.push(current);
      current = { slug: match[1], group, lines: [line] };
    } else if (current) {
      current.lines.push(line);
    }
  }
  if (current) entries.push(current);

  const filled = entries.filter((entry) => {
    const review = entry.lines.find((line) => /^\s*Review:\s*\S/.test(line));
    if (!review) return false;
    entry.review = review.replace(/^\s*Review:\s*/, "");
    return true;
  });
  for (const entry of filled) {
    process.stdout.write(`${entry.slug} (${entry.group}): ${entry.review}\n`);
  }
  process.stdout.write(`${filled.length} of ${entries.length} entries have a filled-in Review: line\n`);
}

function usage() {
  process.stderr.write(
    "Usage: node tools/tasklist-query.mjs <command>\n" +
      "Commands: next, list, group <fixes|workflow|gui-ux|major>, find <text>, reviews\n",
  );
}

function main() {
  const [command, ...args] = process.argv.slice(2);
  if (command === "next" && args.length === 0) return next();
  if (command === "list" && args.length === 0) return process.stdout.write(`${listGroups(GROUPS).join("\n")}\n`);
  if (command === "group" && args.length === 1) {
    const group = GROUPS.find(({ key }) => key === args[0]);
    if (group) return process.stdout.write(`${listGroups([group]).join("\n")}\n`);
  }
  if (command === "find" && args.length > 0) return find(args.join(" "));
  if (command === "reviews" && args.length === 0) return reviews();
  usage();
  process.exit(1);
}

main();
