import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const REPO_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export const TASKLIST_DIR = path.join(REPO_ROOT, "tasklist");

// Fixed group order, matching the layout CLAUDE.md's "Tasklist routine" mandates.
export const GROUPS = [
  { key: "fixes", heading: "FIXES" },
  { key: "workflow", heading: "WORKFLOW" },
  { key: "gui-ux", heading: "GUI & UX" },
  { key: "major", heading: "MAJOR" },
];

export const OPEN_FIELDS = new Set(["Title", "Prio", "Goal", "Files", "Steps", "Open"]);
export const DONE_FIELDS = new Set(["Title", "Completed", "Commit", "Result"]);
const FIELD_RE = /^([A-Za-z]+):\s?(.*)$/;

// A task file's fields can span several lines; anything that is not itself a recognized
// "Label:" line continues the field above it (see the task file format in CLAUDE.md).
export function parseFields(text, knownLabels) {
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
export function joinChunks(chunks) {
  let out = "";
  for (const chunk of chunks) {
    if (out === "" || /[-/]$/.test(out)) out += chunk;
    else out += ` ${chunk}`;
  }
  return out;
}

export function readTasks(dir, knownLabels) {
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

export function sortOpenTasks(tasks) {
  return tasks.sort((a, b) => {
    const prioA = Number(a.fields.Prio ?? Number.MAX_SAFE_INTEGER);
    const prioB = Number(b.fields.Prio ?? Number.MAX_SAFE_INTEGER);
    if (prioA !== prioB) return prioA - prioB;
    return a.slug.localeCompare(b.slug);
  });
}

export function gitTimestamp(filePath) {
  try {
    const out = execFileSync("git", ["-c", "safe.directory=*", "log", "-1", "--format=%ct", "--", filePath], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    }).trim();
    return out ? Number(out) : 0;
  } catch {
    return 0;
  }
}

export function sortDoneTasks(tasks) {
  return tasks.sort((a, b) => {
    const dateA = a.fields.Completed || "";
    const dateB = b.fields.Completed || "";
    if (dateA !== dateB) return dateA < dateB ? 1 : -1;
    if (a.timestamp !== b.timestamp) return b.timestamp - a.timestamp;
    return a.slug.localeCompare(b.slug);
  });
}
