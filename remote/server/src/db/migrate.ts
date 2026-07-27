import { pathToFileURL } from "node:url";
import { migrate as migratePglite } from "drizzle-orm/pglite/migrator";
import { migrate as migratePostgres } from "drizzle-orm/node-postgres/migrator";
import { client, db, usingPostgres } from "./client.js";

const migrationsFolder = "./drizzle";

/** Applies generated PostgreSQL migrations using the active database driver. */
export async function runMigrations(): Promise<void> {
  if (usingPostgres) {
    await migratePostgres(db as Parameters<typeof migratePostgres>[0], { migrationsFolder });
  } else {
    await migratePglite(db as Parameters<typeof migratePglite>[0], { migrationsFolder });
  }
}

const invokedPath = process.argv[1];
if (invokedPath !== undefined && import.meta.url === pathToFileURL(invokedPath).href) {
  runMigrations()
    .then(async () => {
      console.info("Database migrations applied successfully.");
      if ("end" in client) await client.end(); else await client.close();
    })
    .catch(async (error: unknown) => {
      console.error("Database migration failed.", error);
      if ("end" in client) await client.end(); else await client.close();
      process.exitCode = 1;
    });
}
