// Database backup with rotation. Dependency-free (Node built-ins only).
//
//   node scripts/backup.mjs
//
// With DATABASE_URL set (production/Postgres) it runs `pg_dump -Fc` (requires the Postgres client
// tools on the host). Without it (development/PGlite) it snapshots the DATA_DIR directory. Old backups
// beyond BACKUP_KEEP (default 14) are removed. Configure via env: DATABASE_URL, DATA_DIR, BACKUP_DIR
// (default ./backups), BACKUP_KEEP.
import { spawn } from "node:child_process";
import { cp, mkdir, readdir, rm, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";

try {
  process.loadEnvFile();
} catch {
  // no .env; use the ambient environment
}

const backupDir = resolve(process.env.BACKUP_DIR ?? "./backups");
const keep = Math.max(1, Number(process.env.BACKUP_KEEP ?? "14") || 14);
const stamp = new Date().toISOString().replace(/[:.]/g, "-");

function run(cmd, args, opts = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(cmd, args, { stdio: "inherit", ...opts });
    child.on("error", reject);
    child.on("close", (code) => (code === 0 ? resolvePromise() : reject(new Error(`${cmd} exited ${code}`))));
  });
}

async function rotate(prefix) {
  const entries = await readdir(backupDir).catch(() => []);
  const mine = entries.filter((name) => name.startsWith(prefix)).sort(); // ISO stamp sorts chronologically
  const excess = mine.slice(0, Math.max(0, mine.length - keep));
  for (const name of excess) {
    await rm(join(backupDir, name), { recursive: true, force: true });
    console.log(`removed old backup: ${name}`);
  }
}

async function main() {
  await mkdir(backupDir, { recursive: true });

  if (process.env.DATABASE_URL) {
    const outFile = join(backupDir, `db-${stamp}.dump`);
    console.log(`Postgres backup -> ${outFile}`);
    // -Fc = custom compressed format (restore with pg_restore). The URL is passed via --dbname.
    await run("pg_dump", ["-Fc", "--dbname", process.env.DATABASE_URL, "--file", outFile]);
    await rotate("db-");
    console.log("Postgres backup complete.");
    return;
  }

  const dataDir = resolve(process.env.DATA_DIR ?? "./.data");
  if (!existsSync(dataDir)) {
    console.error(`No DATABASE_URL and DATA_DIR does not exist (${dataDir}); nothing to back up.`);
    process.exit(1);
  }
  const st = await stat(dataDir);
  if (!st.isDirectory()) {
    console.error(`DATA_DIR is not a directory: ${dataDir}`);
    process.exit(1);
  }
  const dest = join(backupDir, `pglite-${stamp}`);
  console.log(`PGlite snapshot -> ${dest} (note: for a fully consistent snapshot, stop the server first)`);
  await cp(dataDir, dest, { recursive: true });
  await rotate("pglite-");
  console.log("PGlite snapshot complete.");
}

main().catch((error) => {
  console.error("Backup failed:", error.message);
  process.exit(1);
});
