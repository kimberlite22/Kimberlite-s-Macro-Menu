import { PGlite } from "@electric-sql/pglite";
import { drizzle as drizzlePglite } from "drizzle-orm/pglite";
import { drizzle as drizzlePostgres } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import { env, usePostgres } from "../env.js";
import { schema } from "./schema.js";

export const usingPostgres = usePostgres();

const postgresClient = usingPostgres
  ? new Pool({ connectionString: env.DATABASE_URL })
  : undefined;
const pgliteClient = usingPostgres ? undefined : new PGlite(env.DATA_DIR);

/** Raw driver client, exposed for migrations and orderly shutdown. */
export const client: Pool | PGlite = postgresClient ?? pgliteClient!;

/** Drizzle database using the same PostgreSQL schema for both supported drivers. */
export const db = postgresClient
  ? drizzlePostgres(postgresClient, { schema })
  : drizzlePglite(pgliteClient!, { schema });

/** Closes whichever database client was selected by the environment. */
export async function closeDb(): Promise<void> {
  if (postgresClient) {
    await postgresClient.end();
  } else {
    await pgliteClient!.close();
  }
}
