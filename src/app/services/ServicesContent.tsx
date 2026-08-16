"use client";

import { motion } from "framer-motion";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import SectionHeading from "@/components/ui/SectionHeading";
import ServiceIcon from "@/components/ui/ServiceIcon";
import ServiceRequestForm from "@/components/forms/ServiceRequestForm";
import { FIRST_TIME_OFFER } from "@/lib/constants";
import {
  CurrencyToggle,
  useCurrency,
} from "@/components/providers/CurrencyProvider";

interface Service {
  id: string;
  title: string;
  slug: string;
  description: string;
  features: string;
  priceFrom: number;
  priceTo: number;
  estimatedDays: number;
  icon: string;
  popular: boolean;
}

interface ServicesContentProps {
  services: Service[];
}

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.12 },
  },
};

const item = {
  hidden: { opacity: 0, y: 30 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

export default function ServicesContent({ services }: ServicesContentProps) {
  const { format } = useCurrency();

  return (
    <>
      <section className="bg-gradient-to-b from-brand-50 to-surface-0 py-20">
        <div className="mx-auto max-w-7xl px-6 text-center">
          <Badge variant="pop" className="mb-4">
            {FIRST_TIME_OFFER.discount}% off first project — {FIRST_TIME_OFFER.code}
          </Badge>
          <h1 className="text-4xl font-bold tracking-tight text-surface-900 sm:text-5xl">
            My{" "}
            <span className="bg-gradient-to-r from-brand-600 to-accent-500 bg-clip-text text-transparent">
              Services
            </span>
          </h1>
          <p className="mt-4 text-lg text-surface-500 max-w-2xl mx-auto">
            From concept to launch, I deliver end-to-end web solutions.
            Every project includes a detailed proposal with pricing and timeline
            estimates.
          </p>
          <div className="mt-6 flex justify-center">
            <CurrencyToggle />
          </div>
        </div>
      </section>

      <section className="py-16 bg-surface-0">
        <div className="mx-auto max-w-7xl px-6">
          <motion.div
            variants={container}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-100px" }}
            className="grid gap-8 md:grid-cols-2 lg:grid-cols-3"
          >
            {services.map((service) => (
              <motion.div key={service.id} variants={item}>
                <Card gradient className="relative h-full flex flex-col">
                  {service.popular && (
                    <div className="absolute -top-3 right-6 rounded-full bg-gradient-to-r from-accent-500 to-brand-500 px-3 py-1 text-xs font-semibold text-white shadow-lg">
                      Most Popular
                    </div>
                  )}

                  <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-50 to-accent-50 text-brand-600">
                    <ServiceIcon name={service.icon} className="h-7 w-7" />
                  </div>

                  <h3 className="text-xl font-semibold text-surface-900">
                    {service.title}
                  </h3>

                  <p className="mt-2 text-sm text-surface-500 leading-relaxed">
                    {service.description}
                  </p>

                  <div className="mt-4 space-y-2">
                    {service.features.split(",").map((feature) => (
                      <div
                        key={feature}
                        className="flex items-center gap-2 text-sm text-surface-600"
                      >
                        <svg
                          className="h-4 w-4 text-success-500 shrink-0"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M4.5 12.75l6 6 9-13.5"
                          />
                        </svg>
                        {feature.trim()}
                      </div>
                    ))}
                  </div>

                  <div className="mt-6 pt-4 border-t border-surface-100">
                    <div className="flex items-baseline justify-between">
                      <div>
                        <span className="text-sm text-surface-400">From</span>
                        <div className="text-2xl font-bold text-brand-600">
                          {format(service.priceFrom)}
                        </div>
                        <span className="text-xs text-surface-400">
                          up to {format(service.priceTo)}
                        </span>
                      </div>
                      <div className="text-right">
                        <span className="text-sm text-surface-400">Delivery</span>
                        <div className="text-lg font-semibold text-surface-700">
                          ~{service.estimatedDays} days
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      <section id="request" className="py-16 bg-gradient-to-b from-surface-50 to-surface-0">
        <div className="mx-auto max-w-3xl px-6">
          <SectionHeading
            eyebrow="Get Started"
            title="Request a Service"
            description="Fill out the form below and I'll get back to you within 24 hours with a detailed proposal and quote."
          />

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <Card hover={false} className="p-8">
              <ServiceRequestForm services={services} />
            </Card>
          </motion.div>
        </div>
      </section>
    </>
  );
}
