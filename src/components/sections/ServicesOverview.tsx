"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import SectionHeading from "@/components/ui/SectionHeading";
import ServiceIcon from "@/components/ui/ServiceIcon";
import { useCurrency } from "@/components/providers/CurrencyProvider";

interface Service {
  id: string;
  title: string;
  slug: string;
  description: string;
  priceFrom: number;
  estimatedDays: number;
  icon: string;
  popular: boolean;
}

interface ServicesOverviewProps {
  services: Service[];
}

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
};

const item = {
  hidden: { opacity: 0, y: 30 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

export default function ServicesOverview({ services }: ServicesOverviewProps) {
  const { format } = useCurrency();

  return (
    <section className="py-24 bg-gradient-to-b from-surface-50 to-surface-0">
      <div className="mx-auto max-w-7xl px-6">
        <SectionHeading
          eyebrow="What I Offer"
          title="My Services"
          description="From concept to launch, I provide end-to-end web development services tailored to your business needs."
        />

        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-100px" }}
          className="grid gap-6 md:grid-cols-2 lg:grid-cols-3"
        >
          {services.map((service) => (
            <motion.div key={service.id} variants={item}>
              <Card className="relative h-full">
                {service.popular && (
                  <div className="absolute -top-3 right-6 rounded-full bg-gradient-to-r from-accent-500 to-brand-500 px-3 py-1 text-xs font-semibold text-white shadow-lg">
                    Popular
                  </div>
                )}
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                  <ServiceIcon name={service.icon} className="h-6 w-6" />
                </div>
                <h3 className="text-lg font-semibold text-surface-900">
                  {service.title}
                </h3>
                <p className="mt-2 text-sm text-surface-500 leading-relaxed">
                  {service.description}
                </p>
                <div className="mt-4 flex items-baseline gap-1">
                  <span className="text-sm text-surface-400">From</span>
                  <span className="text-2xl font-bold text-brand-600">
                    {format(service.priceFrom)}
                  </span>
                </div>
                <div className="mt-1 text-xs text-surface-400">
                  ~{service.estimatedDays} days delivery
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>

        <div className="mt-12 text-center">
          <Link href="/services">
            <Button variant="primary" size="lg">
              Explore All Services
            </Button>
          </Link>
        </div>
      </div>
    </section>
  );
}
