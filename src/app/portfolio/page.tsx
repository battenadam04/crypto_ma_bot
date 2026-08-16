import type { Metadata } from "next";
import { prisma } from "@/lib/db";
import PortfolioGrid from "./PortfolioGrid";

export const metadata: Metadata = {
  title: "Portfolio",
  description:
    "Explore our portfolio of web applications, e-commerce solutions, and digital experiences. See the projects that have helped businesses grow.",
};

export default async function PortfolioPage() {
  const projects = await prisma.project.findMany({
    orderBy: { order: "asc" },
  });

  const allTags = Array.from(
    new Set(projects.flatMap((p) => p.tags.split(",").map((t) => t.trim()))),
  );

  return (
    <>
      <section className="bg-gradient-to-b from-brand-50 to-surface-0 py-20">
        <div className="mx-auto max-w-7xl px-6 text-center">
          <h1 className="text-4xl font-bold tracking-tight text-surface-900 sm:text-5xl">
            Our{" "}
            <span className="bg-gradient-to-r from-brand-600 to-accent-500 bg-clip-text text-transparent">
              Portfolio
            </span>
          </h1>
          <p className="mt-4 text-lg text-surface-500 max-w-2xl mx-auto">
            A showcase of projects we&apos;ve built for businesses across various
            industries. Each project is crafted with care, performance, and user
            experience in mind.
          </p>
        </div>
      </section>

      <PortfolioGrid projects={projects} tags={allTags} />
    </>
  );
}
