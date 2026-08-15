"use client";

import { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { motion, AnimatePresence } from "framer-motion";
import {
  serviceRequestSchema,
  type ServiceRequestData,
} from "@/lib/validations";
import { BUDGET_OPTIONS, TIMELINE_OPTIONS } from "@/lib/constants";
import Input from "@/components/ui/Input";
import Textarea from "@/components/ui/Textarea";
import Select from "@/components/ui/Select";
import Button from "@/components/ui/Button";

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
    } catch (err) {
      setStatus("error");
      setErrorMessage(
        err instanceof Error ? err.message : "Something went wrong",
      );
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6" noValidate>
      <div className="grid gap-6 sm:grid-cols-2">
        <Input
          id="request-name"
          label="Full Name *"
          placeholder="John Doe"
          error={errors.name?.message}
          {...register("name")}
        />
        <Input
          id="request-email"
          label="Email *"
          type="email"
          placeholder="john@example.com"
          error={errors.email?.message}
          {...register("email")}
        />
      </div>

      <div className="grid gap-6 sm:grid-cols-2">
        <Input
          id="request-company"
          label="Company"
          placeholder="Your company name"
          {...register("company")}
        />
        <Input
          id="request-phone"
          label="Phone"
          type="tel"
          placeholder="+1 (555) 123-4567"
          {...register("phone")}
        />
      </div>

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
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-brand-700">
                  Estimated Price Range
                </p>
                <p className="text-xl font-bold text-brand-600">
                  ${selectedService.priceFrom.toLocaleString()} — $
                  {selectedService.priceTo.toLocaleString()}
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
          options={[...BUDGET_OPTIONS]}
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
        placeholder="Tell us about your project requirements, goals, and any specific features you need..."
        rows={6}
        error={errors.description?.message}
        {...register("description")}
      />

      <Button
        type="submit"
        variant="accent"
        size="lg"
        loading={status === "loading"}
        className="w-full"
      >
        Submit Request — Get Free Quote
      </Button>

      <AnimatePresence>
        {status === "success" && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-xl bg-success-50 p-4 text-success-600 text-sm font-medium"
            role="status"
          >
            Your service request has been submitted! We&apos;ll review it and
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
    </form>
  );
}
