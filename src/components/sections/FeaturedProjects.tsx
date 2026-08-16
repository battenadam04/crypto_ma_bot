"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import SectionHeading from "@/components/ui/SectionHeading";

interface Project {
  id: string;
  title: string;
  slug: string;
  description: string;
  imageUrl: string;
  tags: string;
  liveUrl?: string | null;
}

interface FeaturedProjectsProps {
  projects: Project[];
}

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.15 },
  },
};

const item = {
  hidden: { opacity: 0, y: 30 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

export default function FeaturedProjects({ projects }: FeaturedProjectsProps) {
  return (
    <section className="py-24 bg-surface-0">
      <div className="mx-auto max-w-7xl px-6">
        <SectionHeading
          eyebrow="My Work"
          title="Featured Projects"
          description="Take a look at some of my recent work that has helped businesses grow and succeed online."
        />

        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-100px" }}
          className="grid gap-8 md:grid-cols-2 lg:grid-cols-3"
        >
          {projects.map((project) => (
            <motion.div key={project.id} variants={item}>
              <Card gradient className="h-full flex flex-col">
                <div className="relative mb-4 h-48 rounded-xl bg-gradient-to-br from-brand-100 to-accent-100 overflow-hidden flex items-center justify-center">
                  <div className="text-4xl font-bold text-brand-300/50">
                    {project.title.charAt(0)}
                  </div>
                </div>
                <h3 className="text-lg font-semibold text-surface-900">
                  {project.title}
                </h3>
                <p className="mt-2 flex-1 text-sm text-surface-500">
                  {project.description}
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {project.tags.split(",").slice(0, 3).map((tag) => (
                    <Badge key={tag} variant="brand">
                      {tag.trim()}
                    </Badge>
                  ))}
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>

        <div className="mt-12 text-center">
          <Link href="/portfolio">
            <Button variant="outline" size="lg">
              View All Projects
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
              </svg>
            </Button>
          </Link>
        </div>
      </div>
    </section>
  );
}
