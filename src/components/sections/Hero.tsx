"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import Button from "@/components/ui/Button";
import { FIRST_TIME_OFFER } from "@/lib/constants";

const floatingShapes = [
  { size: 72, color: "bg-brand-400/20", top: "10%", left: "5%", delay: 0 },
  { size: 48, color: "bg-accent-400/20", top: "20%", right: "10%", delay: 0.5 },
  { size: 96, color: "bg-pop-400/15", bottom: "20%", left: "15%", delay: 1 },
  { size: 56, color: "bg-brand-300/20", bottom: "30%", right: "5%", delay: 1.5 },
  { size: 40, color: "bg-accent-300/25", top: "50%", left: "50%", delay: 0.8 },
];

const stats = [
  { value: "50+", label: "Projects Delivered" },
  { value: "98%", label: "Client Satisfaction" },
  { value: "5+", label: "Years Experience" },
  { value: "24h", label: "Response Time" },
];

export default function Hero() {
  return (
    <section className="relative min-h-[90vh] flex items-center overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-brand-50 via-surface-0 to-accent-50" />

      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {floatingShapes.map((shape, i) => (
          <motion.div
            key={i}
            className={`absolute rounded-full ${shape.color} blur-xl`}
            style={{
              width: shape.size,
              height: shape.size,
              top: shape.top,
              left: shape.left,
              right: shape.right,
              bottom: shape.bottom,
            }}
            animate={{
              y: [0, -20, 0],
              x: [0, 10, 0],
              scale: [1, 1.1, 1],
            }}
            transition={{
              duration: 4 + i,
              repeat: Infinity,
              delay: shape.delay,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>

      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand-500/20 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-6 py-20 lg:py-32">
        <div className="grid gap-12 lg:grid-cols-2 lg:gap-16 items-center">
          <motion.div
            initial={{ opacity: 0, x: -40 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, ease: "easeOut" }}
          >
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="mb-6"
            >
              <span className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-pop-100 to-pop-50 px-4 py-2 text-sm font-semibold text-pop-700 ring-1 ring-pop-200 animate-pulse-glow">
                <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M5 2a2 2 0 00-2 2v14l3.5-2 3.5 2 3.5-2 3.5 2V4a2 2 0 00-2-2H5zm2.5 3a.5.5 0 000 1h5a.5.5 0 000-1h-5zm0 3a.5.5 0 000 1h5a.5.5 0 000-1h-5zm0 3a.5.5 0 000 1h3a.5.5 0 000-1h-3z" clipRule="evenodd" />
                </svg>
                {FIRST_TIME_OFFER.description} — Use code{" "}
                <code className="font-mono font-bold">{FIRST_TIME_OFFER.code}</code>
              </span>
            </motion.div>

            <h1 className="text-4xl font-extrabold tracking-tight text-surface-900 sm:text-5xl lg:text-6xl xl:text-7xl">
              I Build{" "}
              <span className="bg-gradient-to-r from-brand-600 via-accent-500 to-pop-500 bg-clip-text text-transparent animate-gradient">
                Digital Experiences
              </span>{" "}
              That Drive Growth
            </h1>

            <p className="mt-6 text-lg text-surface-500 leading-relaxed max-w-lg sm:text-xl">
              From stunning websites to powerful web applications — I transform
              your vision into reality with cutting-edge technology and
              pixel-perfect design.
            </p>

            <div className="mt-8 flex flex-col sm:flex-row gap-4">
              <Link href="/services#request">
                <Button size="lg" variant="accent">
                  Start Your Project
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                  </svg>
                </Button>
              </Link>
              <Link href="/portfolio">
                <Button size="lg" variant="outline">
                  View My Work
                </Button>
              </Link>
            </div>

            <div className="mt-12 grid grid-cols-2 gap-6 sm:grid-cols-4">
              {stats.map((stat, i) => (
                <motion.div
                  key={stat.label}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.6 + i * 0.1, duration: 0.5 }}
                >
                  <div className="text-2xl font-bold text-brand-600 sm:text-3xl">
                    {stat.value}
                  </div>
                  <div className="mt-1 text-xs text-surface-500 sm:text-sm">
                    {stat.label}
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.3, ease: "easeOut" }}
            className="relative hidden lg:block"
          >
            <div className="relative">
              <div className="absolute -inset-4 rounded-3xl bg-gradient-to-r from-brand-500/20 via-accent-500/20 to-pop-500/20 blur-2xl" />
              <div className="relative rounded-2xl bg-surface-900 p-6 shadow-2xl ring-1 ring-surface-700">
                <div className="flex gap-2 mb-4">
                  <div className="h-3 w-3 rounded-full bg-error-500" />
                  <div className="h-3 w-3 rounded-full bg-warning-500" />
                  <div className="h-3 w-3 rounded-full bg-success-500" />
                </div>
                <pre className="text-sm text-surface-300 font-mono leading-relaxed overflow-hidden">
                  <code>{`const project = await AdamBatten
  .create({
    design: "pixel-perfect",
    performance: "blazing-fast",
    seo: "optimized",
    animations: "smooth",
  });

// Your vision, my expertise
await project.launch(); 🚀`}</code>
                </pre>
              </div>
            </div>

            <motion.div
              className="absolute -top-6 -right-6 rounded-2xl bg-surface-0 p-4 shadow-xl ring-1 ring-surface-200"
              animate={{ y: [0, -8, 0] }}
              transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-success-50 text-success-500">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                </div>
                <div>
                  <div className="text-sm font-semibold text-surface-900">Project Deployed</div>
                  <div className="text-xs text-surface-400">Just now</div>
                </div>
              </div>
            </motion.div>

            <motion.div
              className="absolute -bottom-4 -left-6 rounded-2xl bg-surface-0 p-4 shadow-xl ring-1 ring-surface-200"
              animate={{ y: [0, -6, 0] }}
              transition={{ duration: 4, repeat: Infinity, ease: "easeInOut", delay: 1 }}
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 text-brand-500">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                  </svg>
                </div>
                <div>
                  <div className="text-sm font-semibold text-surface-900">100/100</div>
                  <div className="text-xs text-surface-400">Lighthouse Score</div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
