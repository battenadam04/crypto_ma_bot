"use client";

import { forwardRef, useId, type TextareaHTMLAttributes } from "react";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, className = "", id: externalId, required, ...props }, ref) => {
    const generatedId = useId();
    const id = externalId || generatedId;
    const errorId = `${id}-error`;
    const isRequired = required || label?.includes("*");

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={id}
            className="mb-1.5 block text-sm font-medium text-surface-700"
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          aria-required={isRequired || undefined}
          className={`w-full rounded-xl border bg-surface-0 px-4 py-3 text-surface-900 placeholder:text-surface-400 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent resize-y min-h-[120px] ${
            error
              ? "border-error-500 focus:ring-error-500"
              : "border-surface-200 hover:border-surface-300"
          } ${className}`}
          {...props}
        />
        {error && (
          <p id={errorId} className="mt-1 text-sm text-error-500" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  },
);

Textarea.displayName = "Textarea";
export default Textarea;
