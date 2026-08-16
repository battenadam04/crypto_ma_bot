"use client";

import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { motion, AnimatePresence } from "framer-motion";
import { contactFormSchema, type ContactFormData } from "@/lib/validations";
import Input from "@/components/ui/Input";
import Textarea from "@/components/ui/Textarea";
import Button from "@/components/ui/Button";

export default function ContactForm() {
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const statusRef = useRef<HTMLDivElement>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ContactFormData>({
    resolver: zodResolver(contactFormSchema),
  });

  const errorCount = Object.keys(errors).length;

  const onSubmit = async (data: ContactFormData) => {
    setStatus("loading");
    setErrorMessage("");

    try {
      const res = await fetch("/api/contact", {
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
      setErrorMessage(err instanceof Error ? err.message : "Something went wrong");
      statusRef.current?.focus();
    }
  };

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="space-y-6"
      noValidate
      aria-label="Contact form"
    >
      {errorCount > 0 && (
        <div className="sr-only" role="alert">
          {errorCount} {errorCount === 1 ? "error" : "errors"} in the form.
          Please correct them before submitting.
        </div>
      )}

      <div className="grid gap-6 sm:grid-cols-2">
        <Input
          id="contact-name"
          label="Name"
          placeholder="John Doe"
          autoComplete="name"
          error={errors.name?.message}
          {...register("name")}
        />
        <Input
          id="contact-email"
          label="Email"
          type="email"
          placeholder="john@example.com"
          autoComplete="email"
          error={errors.email?.message}
          {...register("email")}
        />
      </div>

      <Input
        id="contact-subject"
        label="Subject"
        placeholder="How can I help?"
        error={errors.subject?.message}
        {...register("subject")}
      />

      <Textarea
        id="contact-message"
        label="Message"
        placeholder="Tell me about your project..."
        rows={5}
        error={errors.message?.message}
        {...register("message")}
      />

      <Button
        type="submit"
        variant="primary"
        size="lg"
        loading={status === "loading"}
        className="w-full sm:w-auto"
      >
        Send Message
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
              Thank you! Your message has been sent. I&apos;ll get back to you
              within 24 hours.
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
