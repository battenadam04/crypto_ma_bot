"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";

export type PortalMilestone = {
  id: string;
  title: string;
  description: string;
  status: string;
  order: number;
};

interface PortalProgressProps {
  portalId: string;
  initialMilestones: PortalMilestone[];
  isAdmin: boolean;
  portalStatus: string;
  summary: string;
  title: string;
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  in_progress: "In progress",
  done: "Done",
};

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-surface-100 text-surface-700",
  in_progress: "bg-brand-100 text-brand-800",
  done: "bg-success-50 text-success-600",
};

export default function PortalProgress({
  portalId,
  initialMilestones,
  isAdmin,
  portalStatus,
  summary,
  title,
}: PortalProgressProps) {
  const [milestones, setMilestones] = useState(initialMilestones);
  const [metaStatus, setMetaStatus] = useState(portalStatus);
  const [metaSummary, setMetaSummary] = useState(summary);
  const [metaTitle, setMetaTitle] = useState(title);
  const [newTitle, setNewTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const doneCount = milestones.filter((m) => m.status === "done").length;
  const progress =
    milestones.length === 0
      ? 0
      : Math.round((doneCount / milestones.length) * 100);

  const updateMilestone = async (
    id: string,
    patch: Partial<PortalMilestone>,
  ) => {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`/api/portal/projects/${portalId}/milestones`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, ...patch }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Update failed");
      setMilestones((prev) =>
        prev.map((m) => (m.id === id ? { ...m, ...data.milestone } : m)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSaving(false);
    }
  };

  const addMilestone = async () => {
    if (!newTitle.trim()) return;
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`/api/portal/projects/${portalId}/milestones`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not add");
      setMilestones((prev) => [...prev, data.milestone]);
      setNewTitle("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add");
    } finally {
      setSaving(false);
    }
  };

  const saveMeta = async () => {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`/api/portal/projects/${portalId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: metaTitle,
          summary: metaSummary,
          status: metaStatus,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not save");
      setMetaTitle(data.portal.title);
      setMetaSummary(data.portal.summary);
      setMetaStatus(data.portal.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-full min-h-[28rem] flex-col rounded-2xl border border-surface-200 bg-surface-0">
      <div className="border-b border-surface-200 px-5 py-4">
        <h2 className="text-lg font-semibold text-surface-950">Progress</h2>
        <p className="text-sm text-surface-700">
          {isAdmin
            ? "Update milestones so your client sees live status."
            : "Track where your project is right now."}
        </p>
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-xs font-medium text-surface-700">
            <span>
              {doneCount} of {milestones.length} complete
            </span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-100">
            <div
              className="h-full rounded-full bg-brand-600 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {isAdmin && (
          <div className="space-y-3 rounded-xl border border-surface-200 bg-surface-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-surface-700">
              Admin controls
            </p>
            <Input
              id="portal-title"
              label="Project title"
              value={metaTitle}
              onChange={(e) => setMetaTitle(e.target.value)}
            />
            <label className="block text-sm font-medium text-surface-900">
              Status
              <select
                className="mt-1 w-full rounded-xl border border-surface-200 bg-surface-0 px-3 py-2 text-surface-950"
                value={metaStatus}
                onChange={(e) => setMetaStatus(e.target.value)}
              >
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="completed">Completed</option>
              </select>
            </label>
            <label className="block text-sm font-medium text-surface-900">
              Summary for client
              <textarea
                className="mt-1 w-full rounded-xl border border-surface-200 bg-surface-0 px-3 py-2 text-sm text-surface-950"
                rows={3}
                value={metaSummary}
                onChange={(e) => setMetaSummary(e.target.value)}
              />
            </label>
            <Button
              type="button"
              variant="secondary"
              loading={saving}
              onClick={() => void saveMeta()}
            >
              Save project details
            </Button>
          </div>
        )}

        {!isAdmin && metaSummary && (
          <p className="rounded-xl bg-brand-50 px-4 py-3 text-sm text-surface-800">
            {metaSummary}
          </p>
        )}

        <ol className="space-y-3">
          {milestones.map((m, index) => (
            <li
              key={m.id}
              className="rounded-xl border border-surface-200 px-4 py-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-medium text-surface-500">
                    Step {index + 1}
                  </div>
                  <div className="font-semibold text-surface-950">{m.title}</div>
                  {m.description && (
                    <p className="mt-1 text-sm text-surface-700">
                      {m.description}
                    </p>
                  )}
                </div>
                <span
                  className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_STYLE[m.status] || STATUS_STYLE.pending}`}
                >
                  {STATUS_LABEL[m.status] || m.status}
                </span>
              </div>
              {isAdmin && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {(["pending", "in_progress", "done"] as const).map((s) => (
                    <button
                      key={s}
                      type="button"
                      disabled={saving || m.status === s}
                      onClick={() => void updateMilestone(m.id, { status: s })}
                      className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                        m.status === s
                          ? "bg-brand-600 text-white"
                          : "bg-surface-100 text-surface-700 hover:bg-surface-200"
                      }`}
                    >
                      {STATUS_LABEL[s]}
                    </button>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ol>

        {isAdmin && (
          <div className="flex gap-2">
            <Input
              id="new-milestone"
              label="Add milestone"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g. Content review"
            />
            <div className="flex items-end">
              <Button
                type="button"
                variant="secondary"
                loading={saving}
                onClick={() => void addMilestone()}
              >
                Add
              </Button>
            </div>
          </div>
        )}

        {error && (
          <p className="text-sm text-error-600" role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
