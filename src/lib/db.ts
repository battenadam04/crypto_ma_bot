import { PrismaClient } from "@/generated/prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import fs from "fs";
import path from "path";

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

function resolveDbPath() {
  // Keep path statically scoped under prisma/ for Next.js file tracing
  const fileName =
    process.env.DATABASE_URL?.replace(/^file:(\.\/)?/, "") || "prisma/dev.db";
  const relative = fileName.startsWith("prisma/")
    ? fileName
    : path.posix.join("prisma", path.posix.basename(fileName));
  return path.join(/*turbopackIgnore: true*/ process.cwd(), relative);
}

function createPrismaClient() {
  const dbPath = resolveDbPath();
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const adapter = new PrismaBetterSqlite3({ url: `file:${dbPath}` });
  return new PrismaClient({ adapter });
}

export const prisma = globalForPrisma.prisma ?? createPrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
