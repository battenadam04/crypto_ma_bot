"use client";

import { useEffect, useRef, useState } from "react";
import Button from "@/components/ui/Button";
import Textarea from "@/components/ui/Textarea";

export type PortalMessage = {
  id: string;
  senderRole: string;
  senderName: string;
  body: string;
  createdAt: string;
};

interface PortalChatProps {
  portalId: string;
  initialMessages: PortalMessage[];
  isAdmin: boolean;
}

export default function PortalChat({
  portalId,
  initialMessages,
  isAdmin,
}: PortalChatProps) {
  const [messages, setMessages] = useState(initialMessages);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/portal/projects/${portalId}/messages`);
        if (!res.ok) return;
        const data = await res.json();
        setMessages(data.messages);
      } catch {
        /* ignore poll errors */
      }
    }, 8000);
    return () => clearInterval(timer);
  }, [portalId]);

  const send = async () => {
    if (!body.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/portal/projects/${portalId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not send");
      setMessages((prev) => [...prev, data.message]);
      setBody("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full min-h-[28rem] flex-col rounded-2xl border border-surface-200 bg-surface-0">
      <div className="border-b border-surface-200 px-5 py-4">
        <h2 className="text-lg font-semibold text-surface-950">Messages</h2>
        <p className="text-sm text-surface-700">
          {isAdmin
            ? "Chat with your client about this project."
            : "Chat with Adam about your project."}
        </p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {messages.length === 0 && (
          <p className="text-sm text-surface-600">No messages yet — say hello.</p>
        )}
        {messages.map((m) => {
          const mine =
            (isAdmin && m.senderRole === "admin") ||
            (!isAdmin && m.senderRole === "client");
          return (
            <div
              key={m.id}
              className={`flex ${mine ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                  mine
                    ? "bg-brand-600 text-white"
                    : "bg-surface-100 text-surface-950"
                }`}
              >
                <div
                  className={`mb-1 text-xs font-semibold ${
                    mine ? "text-white/80" : "text-surface-600"
                  }`}
                >
                  {m.senderName}
                </div>
                <p className="whitespace-pre-wrap">{m.body}</p>
                <div
                  className={`mt-1 text-[11px] ${
                    mine ? "text-white/70" : "text-surface-500"
                  }`}
                >
                  {new Date(m.createdAt).toLocaleString()}
                </div>
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-surface-200 p-4 space-y-3">
        <Textarea
          id={`chat-${portalId}`}
          label="Write a message"
          rows={3}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Ask a question or share an update…"
        />
        {error && (
          <p className="text-sm text-error-600" role="alert">
            {error}
          </p>
        )}
        <Button
          type="button"
          variant="primary"
          loading={loading}
          onClick={() => void send()}
        >
          Send
        </Button>
      </div>
    </div>
  );
}
