"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { NAV_LINKS } from "@/lib/constants";
import Button from "@/components/ui/Button";

export default function Header() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeMobile();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen, closeMobile]);

  return (
    <header className="sticky top-0 z-50 border-b border-surface-200/60 bg-surface-0/80 backdrop-blur-xl">
      <nav aria-label="Main navigation" className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2 group" aria-label="Adam Batten home">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-accent-500 text-white font-bold text-lg shadow-lg shadow-brand-500/25 group-hover:shadow-brand-500/40 transition-shadow" aria-hidden="true">
            AB
          </div>
          <span className="text-xl font-bold text-surface-900">
            Adam <span className="text-brand-600">Batten</span>
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-1" role="list">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              role="listitem"
              aria-current={pathname === link.href ? "page" : undefined}
              className={`relative px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                pathname === link.href
                  ? "text-brand-600"
                  : "text-surface-600 hover:text-surface-900 hover:bg-surface-100"
              }`}
            >
              {link.label}
              {pathname === link.href && (
                <motion.div
                  layoutId="activeTab"
                  className="absolute inset-0 rounded-lg bg-brand-50"
                  style={{ zIndex: -1 }}
                  transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                />
              )}
            </Link>
          ))}
        </div>

        <div className="hidden md:flex items-center gap-3">
          <Link href="/services#request">
            <Button size="sm" variant="accent">
              Get a Quote
            </Button>
          </Link>
        </div>

        <button
          type="button"
          className="md:hidden p-2 text-surface-600 hover:text-surface-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 rounded-lg"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-expanded={mobileOpen}
          aria-controls="mobile-menu"
          aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
        >
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            {mobileOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            )}
          </svg>
        </button>
      </nav>

      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            id="mobile-menu"
            role="navigation"
            aria-label="Mobile navigation"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden border-t border-surface-200 bg-surface-0"
          >
            <div className="px-6 py-4 space-y-2">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={closeMobile}
                  aria-current={pathname === link.href ? "page" : undefined}
                  className={`block rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
                    pathname === link.href
                      ? "bg-brand-50 text-brand-600"
                      : "text-surface-600 hover:bg-surface-100 hover:text-surface-900"
                  }`}
                >
                  {link.label}
                </Link>
              ))}
              <Link
                href="/services#request"
                onClick={closeMobile}
                className="block mt-2"
              >
                <Button size="sm" variant="accent" className="w-full">
                  Get a Quote
                </Button>
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
