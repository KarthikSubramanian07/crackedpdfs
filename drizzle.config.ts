
import { defineConfig } from 'drizzle-kit';
import type { Config } from 'drizzle-kit';

const databaseUrl = process.env.TURSO_CONNECTION_URL || 'file:./storage/crackedpdfs.db';
const authToken = process.env.TURSO_AUTH_TOKEN || undefined;
const isLocalFileDatabase = databaseUrl.startsWith('file:');

const dbConfig: Config = defineConfig({
  schema: './src/db/schema.ts',
  out: './drizzle',
  dialect: isLocalFileDatabase ? 'sqlite' : 'turso',
  dbCredentials: isLocalFileDatabase
    ? { url: databaseUrl }
    : {
        url: databaseUrl,
        authToken,
      },
} as Config);

export default dbConfig;
