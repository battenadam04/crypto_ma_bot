import { z } from "zod";

export const portalOtpRequestSchema = z.object({
  email: z.string().email("Enter a valid email address"),
});

export const portalOtpVerifySchema = z.object({
  email: z.string().email("Enter a valid email address"),
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, "Enter the 6-digit PIN from your email"),
});

export const portalCreateSchema = z.object({
  title: z.string().min(3, "Title is required"),
  clientName: z.string().min(2, "Client name is required"),
  clientEmail: z.string().email("Valid client email required"),
  summary: z.string().optional(),
  milestones: z
    .array(
      z.object({
        title: z.string().min(2),
        description: z.string().optional(),
      }),
    )
    .optional(),
});

export const portalMessageSchema = z.object({
  body: z.string().trim().min(1, "Message cannot be empty").max(4000),
});

export const portalMilestoneUpdateSchema = z.object({
  title: z.string().min(2).optional(),
  description: z.string().optional(),
  status: z.enum(["pending", "in_progress", "done"]).optional(),
  order: z.number().int().optional(),
});

export const portalMilestoneCreateSchema = z.object({
  title: z.string().min(2),
  description: z.string().optional(),
  status: z.enum(["pending", "in_progress", "done"]).optional(),
});

export const portalMetaUpdateSchema = z.object({
  title: z.string().min(3).optional(),
  summary: z.string().optional(),
  status: z.enum(["active", "paused", "completed"]).optional(),
});
