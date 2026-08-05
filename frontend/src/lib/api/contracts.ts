import { z } from "zod";

export const roles = ["OWNER", "MANAGER", "PHYSIOTHERAPIST", "CUSTOMER"] as const;
export const roleSchema = z.enum(roles);
export type Role = z.infer<typeof roleSchema>;

export type UserSummary = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  mobile_number: string | null;
  profile_image: string;
  roles: string[];
};

export type AccessRole = {
  id: string;
  user_id: string;
  organization_id: string;
  clinic_id: string | null;
  role: Role;
  scope: "organization" | "clinic";
  is_active: boolean;
};

export type AccessSummary = {
  user_id: string;
  organization: { id: string; slug: string };
  permitted_clinics: Array<{ id: string; slug: string }>;
  roles: AccessRole[];
};

export type Session = { user: UserSummary; access: AccessSummary };
export type SafeApiError = { detail: string; fieldErrors?: Record<string, string> };
