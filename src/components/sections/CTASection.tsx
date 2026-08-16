"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import Button from "@/components/ui/Button";
import { FIRST_TIME_OFFER } from "@/lib/constants";

export default function CTASection() {
  return (
    <section className="py-24">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-brand-600 via-accent-600 to-pop-600 p-12 lg:p-16 text-center animate-gradient"
        >
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,rgba(255,255,255,0.1),transparent)]" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_80%,rgba(255,255,255,0.08),transparent)]" />

          <div className="relative">
            <motion.div
              initial={{ scale: 0.9 }}
              whileInView={{ scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: 0.2 }}
              className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full bg-white/20 px-4 py-2 text-sm font-semibold text-white backdrop-blur-sm"
            >
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M5 2a2 2 0 00-2 2v14l3.5-2 3.5 2 3.5-2 3.5 2V4a2 2 0 00-2-2H5zm2.5 3a.5.5 0 000 1h5a.5.5 0 000-1h-5zm0 3a.5.5 0 000 1h5a.5.5 0 000-1h-5z" clipRule="evenodd" />
              </svg>
              {FIRST_TIME_OFFER.discount}% off — Code: {FIRST_TIME_OFFER.code}
            </motion.div>

            <h2 className="text-3xl font-bold text-white sm:text-4xl lg:text-5xl">
              Ready to Build Something Amazing?
            </h2>
            <p className="mt-4 text-lg text-white/80 max-w-2xl mx-auto">
              Let&apos;s discuss your project. Get a free consultation and a
              detailed quote within 24 hours. First-time clients enjoy{" "}
              {FIRST_TIME_OFFER.discount}% off their first project.
            </p>
            <div className="mt-8 flex flex-col sm:flex-row gap-4 justify-center">
              <Link href="/services#request">
                <Button
                  size="lg"
                  className="bg-white text-brand-700 hover:bg-white/90 shadow-xl"
                >
                  Get Your Free Quote
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                  </svg>
                </Button>
              </Link>
              <Link href="/portfolio">
                <Button
                  size="lg"
                  className="border-2 border-white/30 text-white hover:bg-white/10 bg-transparent"
                >
                  See My Work
                </Button>
              </Link>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
