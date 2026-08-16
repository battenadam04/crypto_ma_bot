"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import SectionHeading from "@/components/ui/SectionHeading";
import Button from "@/components/ui/Button";

const values = [
  {
    title: "Quality First",
    description:
      "I never cut corners. Every line of code is written with care, tested thoroughly, and optimized for performance.",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
      </svg>
    ),
  },
  {
    title: "Transparent Communication",
    description:
      "Regular updates, clear timelines, and honest conversations. You'll always know where your project stands.",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.059-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
      </svg>
    ),
  },
  {
    title: "Innovation Driven",
    description:
      "I stay ahead of the curve with modern technologies and best practices to deliver cutting-edge solutions.",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
      </svg>
    ),
  },
  {
    title: "Client Success",
    description:
      "Your success is my success. I measure my work by the impact it has on your business growth.",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
      </svg>
    ),
  },
];

const process = [
  {
    step: "01",
    title: "Discovery",
    description:
      "I dive deep into your business goals, target audience, and project requirements to create a comprehensive plan.",
  },
  {
    step: "02",
    title: "Design",
    description:
      "I create wireframes and prototypes that bring your vision to life with pixel-perfect precision.",
  },
  {
    step: "03",
    title: "Development",
    description:
      "I build your project using modern technologies, following best practices for performance and scalability.",
  },
  {
    step: "04",
    title: "Testing & Launch",
    description:
      "Rigorous testing across devices and browsers, followed by a smooth deployment and post-launch support.",
  },
];

const techStack = [
  "React",
  "Next.js",
  "TypeScript",
  "Node.js",
  "PostgreSQL",
  "Tailwind CSS",
  "Prisma",
  "Docker",
  "AWS",
  "Vercel",
  "GraphQL",
  "Redis",
];

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

export default function AboutContent() {
  return (
    <>
      <section className="bg-gradient-to-b from-brand-50 to-surface-0 py-20">
        <div className="mx-auto max-w-7xl px-6">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="text-4xl font-bold tracking-tight text-surface-950 sm:text-5xl">
              About{" "}
              <span className="bg-gradient-to-r from-brand-600 to-accent-500 bg-clip-text text-transparent">
                Adam Batten
              </span>
            </h1>
            <p className="mt-6 text-lg text-surface-500 leading-relaxed">
              I&apos;m a developer and designer who believes that great software
              can transform businesses. With over 5 years of experience and 50+
              projects delivered, I bring expertise and dedication to every
              project.
            </p>
          </div>
        </div>
      </section>

      <section className="py-20 bg-surface-0">
        <div className="mx-auto max-w-7xl px-6">
          <SectionHeading
            eyebrow="My Values"
            title="What Drives Me"
            description="The principles that guide every decision I make and every line of code I write."
          />

          <motion.div
            variants={container}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true }}
            className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4"
          >
            {values.map((v) => (
              <motion.div
                key={v.title}
                variants={item}
                className="rounded-2xl border border-surface-200 bg-surface-0 p-6 text-center hover:shadow-lg hover:shadow-brand-500/5 transition-shadow"
              >
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-100 text-brand-700">
                  {v.icon}
                </div>
                <h3 className="text-lg font-semibold text-surface-950">
                  {v.title}
                </h3>
                <p className="mt-2 text-sm text-surface-700 leading-relaxed">
                  {v.description}
                </p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      <section className="py-20 bg-surface-50">
        <div className="mx-auto max-w-7xl px-6">
          <SectionHeading
            eyebrow="My Process"
            title="How I Work"
            description="A proven 4-step process that ensures every project is delivered on time, on budget, and beyond expectations."
          />

          <div className="relative">
            <div className="absolute left-8 top-0 bottom-0 w-0.5 bg-brand-200 hidden md:block" />
            <motion.div
              variants={container}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true }}
              className="space-y-12"
            >
              {process.map((step) => (
                <motion.div
                  key={step.step}
                  variants={item}
                  className="relative flex gap-6 md:gap-8"
                >
                  <div className="relative z-10 flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-accent-500 text-white font-bold text-lg shadow-lg shadow-brand-500/25">
                    {step.step}
                  </div>
                  <div className="pt-2">
                    <h3 className="text-xl font-semibold text-surface-950">
                      {step.title}
                    </h3>
                    <p className="mt-2 text-surface-700 leading-relaxed max-w-lg">
                      {step.description}
                    </p>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </div>
      </section>

      <section className="py-20 bg-surface-0">
        <div className="mx-auto max-w-7xl px-6">
          <SectionHeading
            eyebrow="Tech Stack"
            title="Technologies I Use"
            description="I use modern, battle-tested technologies to build robust and scalable solutions."
          />

          <motion.div
            variants={container}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true }}
            className="flex flex-wrap justify-center gap-4"
          >
            {techStack.map((tech) => (
              <motion.div
                key={tech}
                variants={item}
                whileHover={{ scale: 1.05 }}
                className="rounded-xl bg-surface-0 border border-surface-200 px-6 py-3 text-sm font-semibold text-surface-950 shadow-sm hover:shadow-md hover:border-brand-200 transition-all"
              >
                {tech}
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      <section className="py-20 bg-gradient-to-b from-surface-0 to-surface-50">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h2 className="text-3xl font-bold text-surface-950 sm:text-4xl">
            Ready to start your project?
          </h2>
          <p className="mt-4 text-lg text-surface-700">
            Let&apos;s discuss your ideas and turn them into reality.
          </p>
          <div className="mt-8 flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/services#request">
              <Button size="lg" variant="accent">
                Get a Free Quote
              </Button>
            </Link>
            <Link href="/contact">
              <Button size="lg" variant="outline">
                Contact Me
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
