"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  gradient?: boolean;
}

export default function Card({
  children,
  className = "",
  hover = true,
  gradient = false,
}: CardProps) {
  return (
    <motion.div
      whileHover={hover ? { y: -4, scale: 1.01 } : undefined}
      transition={{ duration: 0.2 }}
      className={`rounded-2xl border border-surface-200 bg-surface-0 p-6 ${
        hover ? "hover:shadow-xl hover:shadow-brand-500/10" : ""
      } ${
        gradient
          ? "bg-gradient-to-br from-surface-0 via-brand-50/30 to-accent-50/20"
          : ""
      } transition-shadow duration-300 ${className}`}
    >
      {children}
    </motion.div>
  );
}
