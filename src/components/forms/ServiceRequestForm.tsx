"use client";

import { useState, useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { motion, AnimatePresence } from "framer-motion";
import {
  serviceRequestSchema,
  type ServiceRequestData,
} from "@/lib/validations";
import { TIMELINE_OPTIONS } from "@/lib/constants";
import Input from "@/components/ui/Input";
import Textarea from "@/components/ui/Textarea";
import Select from "@/components/ui/Select";
import Button from "@/components/ui/Button";
import { useCurrency } from "@/components/providers/CurrencyProvider";

interface ServiceOption {
  id: string;
  title: string;
  priceFrom: number;
  priceTo: number;
  estimatedDays: number;
}

interface ServiceRequestFormProps {
  services: ServiceOption[];
  preselectedServiceId?: string;
}

export default function ServiceRequestForm({
  services,
  preselectedServiceId,
}: ServiceRequestFormProps) {
  const [status, setStatus] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [selectedService, setSelectedService] = useState<ServiceOption | null>(
    null,
  );
  const statusRef = useRef<HTMLDivElement>(null);
  const { format, budgetOptions } = useCurrency();

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors },
  } = useForm<ServiceRequestData>({
    resolver: zodResolver(serviceRequestSchema),
    defaultValues: {
      serviceId: preselectedServiceId || "",
    },
  });

  const watchedServiceId = watch("serviceId");
  const errorCount = Object.keys(errors).length;

  useEffect(() => {
    if (preselectedServiceId) {
      setValue("serviceId", preselectedServiceId);
    }
  }, [preselectedServiceId, setValue]);

  useEffect(() => {
    const found = services.find((s) => s.id === watchedServiceId);
    setSelectedService(found || null);
  }, [watchedServiceId, services]);

  const serviceOptions = services.map((s) => ({
    value: s.id,
    label: s.title,
  }));

  const onSubmit = async (data: ServiceRequestData) => {
    setStatus("loading");
    setErrorMessage("");

    try {
      const res = await fetch("/api/service-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });

      if (!res.ok) {
        const body = await res.json();
        throw new Error(body.error || "Something went wrong");
      }

      setStatus("success");
      reset();
      statusRef.current?.focus();
    } catch (err) {
      setStatus("error");
      setErrorMessage(
        err instanceof Error ? err.message : "Something went wrong",
      );
      statusRef.current?.focus();
    }
  };

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="space-y-6"
      noValidate
      aria-label="Service request form"
    >
      {errorCount > 0 && (
        <div className="sr-only" role="alert">
          {errorCount} {errorCount === 1 ? "error" : "errors"} in the form.
          Please correct them before submitting.
        </div>
      )}

      <fieldset className="space-y-6">
        <legend className="text-lg font-semibold text-surface-950 mb-2">
          Your Details
        </legend>
        <div className="grid gap-6 sm:grid-cols-2">
          <Input
            id="request-name"
            label="Full Name *"
            placeholder="John Doe"
            autoComplete="name"
            error={errors.name?.message}
            {...register("name")}
          />
          <Input
            id="request-email"
            label="Email *"
            type="email"
            placeholder="john@example.com"
            autoComplete="email"
            error={errors.email?.message}
            {...register("email")}
          />
        </div>

        <div className="grid gap-6 sm:grid-cols-2">
          <Input
            id="request-company"
            label="Company"
            placeholder="Your company name"
            autoComplete="organization"
            {...register("company")}
          />
          <Input
            id="request-phone"
            label="Phone"
            type="tel"
            placeholder="+1 (555) 123-4567"
            autoComplete="tel"
            {...register("phone")}
          />
        </div>
      </fieldset>

      <fieldset className="space-y-6">
        <legend className="text-lg font-semibold text-surface-950 mb-2">
          Project Details
        </legend>

        <Select
          id="request-service"
          label="Service *"
          placeholder="Select a service"
          options={serviceOptions}
          error={errors.serviceId?.message}
          {...register("serviceId")}
        />

        <AnimatePresence>
          {selectedService && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="rounded-xl bg-brand-50 p-4 border border-brand-100"
              role="region"
              aria-label="Pricing estimate for selected service"
              aria-live="polite"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-brand-700">
                    Estimated Price Range
                  </p>
                  <p className="text-xl font-bold text-brand-600">
                    {format(selectedService.priceFrom)} —{" "}
                    {format(selectedService.priceTo)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-brand-700">
                    Estimated Delivery
                  </p>
                  <p className="text-xl font-bold text-brand-600">
                    ~{selectedService.estimatedDays} days
                  </p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="grid gap-6 sm:grid-cols-2">
          <Select
            id="request-budget"
            label="Budget Range"
            placeholder="Select budget range"
            options={budgetOptions}
            {...register("budget")}
          />
          <Select
            id="request-timeline"
            label="Preferred Timeline"
            placeholder="Select timeline"
            options={[...TIMELINE_OPTIONS]}
            {...register("timeline")}
          />
        </div>

        <Textarea
          id="request-description"
          label="Project Description *"
          placeholder="Tell me about your project requirements, goals, and any specific features you need..."
          rows={6}
          error={errors.description?.message}
          {...register("description")}
        />
      </fieldset>

      <Button
        type="submit"
        variant="accent"
        size="lg"
        loading={status === "loading"}
        className="w-full"
      >
        Submit Request — Get Free Quote
      </Button>

      <div
        ref={statusRef}
        tabIndex={-1}
        aria-live="polite"
        aria-atomic="true"
        className="outline-none"
      >
        <AnimatePresence>
          {status === "success" && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="rounded-xl bg-success-50 p-4 text-success-600 text-sm font-medium"
              role="status"
            >
              Your service request has been submitted! I&apos;ll review it and
              get back to you with a detailed quote within 24 hours.
            </motion.div>
          )}

          {status === "error" && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="rounded-xl bg-error-50 p-4 text-error-500 text-sm font-medium"
              role="alert"
            >
              {errorMessage}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </form>
  );
}
