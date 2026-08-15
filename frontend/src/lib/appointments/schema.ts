import { z } from "zod";

export const appointmentSchema = z.object({
  patient_name: z.string().trim().min(2).max(160),
  age: z.coerce.number().int().min(1).max(120),
  gender: z.enum(["FEMALE", "MALE", "OTHER", "PREFER_NOT_TO_SAY"]),
  mobile_number: z.string().regex(/^[6-9]\d{9}$/, "Enter a valid 10-digit Indian mobile number."),
  alternate_mobile: z.union([z.literal(""), z.string().regex(/^[6-9]\d{9}$/)]),
  email: z.union([z.literal(""), z.email()]),
  therapy: z.string().uuid(),
  requested_therapies: z.array(z.string().uuid()).default([]),
  session_preference: z.enum(["SINGLE", "PACKAGE"]),
  preferred_date: z.string().min(1),
  preferred_time: z.string().min(1),
  preferred_practitioner: z.string().uuid().or(z.literal("")).optional(),
  problem_description: z.string().trim().min(10).max(2000),
  pain_area: z.string().trim().min(2).max(160),
  problem_duration: z.string().trim().min(2).max(120),
  doctor_reference: z.string().max(255),
  address: z.string().trim().min(10).max(500),
  city: z.string().trim().min(2).max(120),
  pin_code: z.string().regex(/^[1-9]\d{5}$/),
  landmark: z.string().trim().min(2).max(255),
  google_map_link: z.union([z.literal(""), z.url()]),
});
export type AppointmentFormValues = z.infer<typeof appointmentSchema>;
