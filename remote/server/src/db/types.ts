import type { PgDatabase } from "drizzle-orm/pg-core";
import type { PgQueryResultHKT } from "drizzle-orm/pg-core/session";
import type { schema } from "./schema.js";

/** Common Postgres Drizzle surface shared by the PGlite and node-postgres drivers. */
export type Database = PgDatabase<PgQueryResultHKT, typeof schema>;
