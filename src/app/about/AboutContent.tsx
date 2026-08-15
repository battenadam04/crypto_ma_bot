"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import SectionHeading from "@/components/ui/SectionHeading";
import Button from "@/components/ui/Button";

const values = [
  {
    title: "Quality First",
    description:
      "We never cut corners. Every line of code is written with care, tested thoroughly, and optimized for performance.",
    icon: "✦",
  },
  {
    title: "Transparent Communication",
    description:
      "Regular updates, clear timelines, and honest conversations. You'll always know where your project stands.",
    icon: "💬",
  },
  {
    title: "Innovation Driven",
    description:
      "We stay ahead of the curve with modern technologies and best practices to deliver cutting-edge solutions.",
    icon: "🚀",
  },
  {
    title: "Client Success",
    description:
      "Your success is our success. We measure our work by the impact it has on your business growth.",
    icon: "📈",
  },
];

const process = [
  {
    step: "01",
    title: "Discovery",
    description:
      "We dive deep into your business goals, target audience, and project requirements to create a comprehensive plan.",
  },
  {
    step: "02",
    title: "Design",
    description:
      "Our designers create wireframes and prototypes that bring your vision to life with pixel-perfect precision.",
  },
  {
    step: "03",
    title: "Development",
    description:
      "We build your project using modern technologies, following best practices for performance and scalability.",
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
            <h1 className="text-4xl font-bold tracking-tight text-surface-900 sm:text-5xl">
              About{" "}
              <span className="bg-gradient-to-r from-brand-600 to-accent-500 bg-clip-text text-transparent">
                DevCraft Studio
              </span>
            </h1>
            <p className="mt-6 text-lg text-surface-500 leading-relaxed">
              We&apos;re a passionate team of developers, designers, and
              strategists who believe that great software can transform
              businesses. With over 5 years of experience and 50+ projects
              delivered, we bring expertise and dedication to every project.
            </p>
          </div>
        </div>
      </section>

      <section className="py-20">
        <div className="mx-auto max-w-7xl px-6">
          <SectionHeading
            eyebrow="Our Values"
            title="What Drives Us"
            description="The principles that guide every decision we make and every line of code we write."
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
                <div className="mb-4 text-4xl">{v.icon}</div>
                <h3 className="text-lg font-semibold text-surface-900">
                  {v.title}
                </h3>
                <p className="mt-2 text-sm text-surface-500 leading-relaxed">
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
            eyebrow="Our Process"
            title="How We Work"
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
                    <h3 className="text-xl font-semibold text-surface-900">
                      {step.title}
                    </h3>
                    <p className="mt-2 text-surface-500 leading-relaxed max-w-lg">
                      {step.description}
                    </p>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </div>
      </section>

      <section className="py-20">
        <div className="mx-auto max-w-7xl px-6">
          <SectionHeading
            eyebrow="Tech Stack"
            title="Technologies We Use"
            description="We use modern, battle-tested technologies to build robust and scalable solutions."
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
                className="rounded-xl bg-surface-0 border border-surface-200 px-6 py-3 text-sm font-medium text-surface-700 shadow-sm hover:shadow-md hover:border-brand-200 transition-all"
              >
                {tech}
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      <section className="py-20 bg-gradient-to-b from-surface-0 to-surface-50">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h2 className="text-3xl font-bold text-surface-900 sm:text-4xl">
            Ready to start your project?
          </h2>
          <p className="mt-4 text-lg text-surface-500">
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
                Contact Us
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
