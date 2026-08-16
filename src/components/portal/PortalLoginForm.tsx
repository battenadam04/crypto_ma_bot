"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";

type Step = "email" | "pin";

export default function PortalLoginForm() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");
  const [devCode, setDevCode] = useState<string | null>(null);

  const requestPin = async () => {
    setStatus("loading");
    setMessage("");
    setDevCode(null);
    try {
      const res = await fetch("/api/portal/otp/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || "Could not send PIN");
      if (body.devCode) setDevCode(body.devCode);
      setMessage(body.message || "Check your email for a PIN.");
      setStep("pin");
      setStatus("idle");
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Something went wrong");
    }
  };

  const verifyPin = async () => {
    setStatus("loading");
    setMessage("");
    try {
      const res = await fetch("/api/portal/otp/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || "Invalid PIN");
      router.push("/portal/home");
      router.refresh();
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Something went wrong");
    }
  };

  return (
    <div className="mx-auto w-full max-w-md space-y-6 rounded-2xl border border-surface-200 bg-surface-0 p-8 shadow-sm">
      <div>
        <h1 className="text-2xl font-bold text-surface-950">Client portal</h1>
        <p className="mt-2 text-sm text-surface-700">
          No password needed. I&apos;ll email you a one-time PIN to sign in.
        </p>
      </div>

      {step === "email" ? (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void requestPin();
          }}
        >
          <Input
            id="portal-email"
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            required
          />
          <Button
            type="submit"
            variant="primary"
            size="lg"
            className="w-full"
            loading={status === "loading"}
          >
            Email me a PIN
          </Button>
        </form>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void verifyPin();
          }}
        >
          <p className="text-sm text-surface-700">
            PIN sent to <strong className="text-surface-950">{email}</strong>
          </p>
          <Input
            id="portal-pin"
            label="6-digit PIN"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder="123456"
            required
          />
          <Button
            type="submit"
            variant="primary"
            size="lg"
            className="w-full"
            loading={status === "loading"}
          >
            Sign in
          </Button>
          <div className="flex flex-wrap gap-3 text-sm">
            <button
              type="button"
              className="font-medium text-brand-700 hover:underline"
              onClick={() => {
                void requestPin();
              }}
            >
              Forgot PIN / send a new one
            </button>
            <button
              type="button"
              className="text-surface-600 hover:underline"
              onClick={() => {
                setStep("email");
                setCode("");
                setMessage("");
                setDevCode(null);
              }}
            >
              Use a different email
            </button>
          </div>
        </form>
      )}

      {message && (
        <p
          className={`text-sm ${status === "error" ? "text-error-600" : "text-surface-700"}`}
          role={status === "error" ? "alert" : "status"}
        >
          {message}
        </p>
      )}

      {devCode && (
        <p className="rounded-lg bg-surface-100 px-3 py-2 text-xs text-surface-700">
          Dev mode (no Resend key): PIN is <strong>{devCode}</strong>
        </p>
      )}
    </div>
  );
}
