"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";

type PortalListItem = {
  id: string;
  title: string;
  clientName: string;
  clientEmail: string;
  status: string;
  updatedAt: string;
  milestones: { status: string }[];
  _count: { messages: number };
};

interface PortalHomeClientProps {
  email: string;
  isAdmin: boolean;
  portals: PortalListItem[];
}

export default function PortalHomeClient({
  email,
  isAdmin,
  portals: initial,
}: PortalHomeClientProps) {
  const router = useRouter();
  const [portals, setPortals] = useState(initial);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [clientName, setClientName] = useState("");
  const [clientEmail, setClientEmail] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const logout = async () => {
    await fetch("/api/portal/logout", { method: "POST" });
    router.push("/portal");
    router.refresh();
  };

  const create = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/portal/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, clientName, clientEmail, summary }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not create");
      setPortals((prev) => [
        {
          ...data.portal,
          _count: { messages: 0 },
        },
        ...prev,
      ]);
      setShowCreate(false);
      setTitle("");
      setClientName("");
      setClientEmail("");
      setSummary("");
      router.push(`/portal/${data.portal.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-8 px-6 py-12">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-surface-950">
            {isAdmin ? "Your client portals" : "Your projects"}
          </h1>
          <p className="mt-2 text-surface-700">
            Signed in as <strong>{email}</strong>
            {isAdmin ? " (admin)" : ""}
          </p>
        </div>
        <div className="flex gap-2">
          {isAdmin && (
            <Button
              type="button"
              variant="primary"
              onClick={() => setShowCreate((v) => !v)}
            >
              {showCreate ? "Cancel" : "New portal"}
            </Button>
          )}
          <Button type="button" variant="ghost" onClick={() => void logout()}>
            Sign out
          </Button>
        </div>
      </div>

      {showCreate && isAdmin && (
        <div className="space-y-4 rounded-2xl border border-surface-200 bg-surface-0 p-6">
          <h2 className="text-lg font-semibold text-surface-950">
            Start a client portal
          </h2>
          <p className="text-sm text-surface-700">
            The client signs in with their email + a PIN. Default milestones are
            added automatically — you can edit them on the project page.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              id="create-title"
              label="Project title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Acme — SEO landing page"
            />
            <Input
              id="create-client-name"
              label="Client name"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
            />
            <Input
              id="create-client-email"
              label="Client email"
              type="email"
              value={clientEmail}
              onChange={(e) => setClientEmail(e.target.value)}
            />
            <Input
              id="create-summary"
              label="Short summary (optional)"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
            />
          </div>
          {error && (
            <p className="text-sm text-error-600" role="alert">
              {error}
            </p>
          )}
          <Button
            type="button"
            variant="primary"
            loading={loading}
            onClick={() => void create()}
          >
            Create portal
          </Button>
        </div>
      )}

      {portals.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-surface-300 bg-surface-50 px-6 py-12 text-center text-surface-700">
          {isAdmin
            ? "No portals yet. Create one when work begins."
            : "No active projects linked to this email yet."}
        </p>
      ) : (
        <ul className="grid gap-4">
          {portals.map((p) => {
            const done = p.milestones.filter((m) => m.status === "done").length;
            const total = p.milestones.length;
            return (
              <li key={p.id}>
                <Link
                  href={`/portal/${p.id}`}
                  className="block rounded-2xl border border-surface-200 bg-surface-0 p-5 transition hover:border-brand-300 hover:shadow-md"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-lg font-semibold text-surface-950">
                      {p.title}
                    </h2>
                    <span className="rounded-full bg-surface-100 px-2.5 py-1 text-xs font-semibold capitalize text-surface-700">
                      {p.status}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-surface-700">
                    {isAdmin
                      ? `${p.clientName} · ${p.clientEmail}`
                      : "Open to chat and view progress"}
                  </p>
                  <p className="mt-3 text-xs text-surface-500">
                    {done}/{total} milestones · {p._count.messages} messages ·
                    updated {new Date(p.updatedAt).toLocaleDateString()}
                  </p>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
