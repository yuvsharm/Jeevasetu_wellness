import { z } from "zod";

const strongPassword = z
  .string()
  .min(12, "Use at least 12 characters.")
  .regex(/[a-z]/, "Include a lowercase letter.")
  .regex(/[A-Z]/, "Include an uppercase letter.")
  .regex(/[0-9]/, "Include a number.");

export const loginSchema = z.object({
  identifier: z.string().trim().min(1, "Enter your email or mobile number."),
  password: z.string().min(1, "Enter your password."),
});

export const registrationSchema = z
  .object({
    first_name: z.string().trim().min(1, "Enter your first name.").max(150),
    last_name: z.string().trim().min(1, "Enter your last name.").max(150),
    mobile_number: z.string().trim().min(8, "Enter a valid international mobile number."),
    email: z.email("Enter a valid email address."),
    password: strongPassword,
    confirm_password: z.string(),
    consent: z.boolean().refine((value) => value, {
      message: "Accept the Terms and Privacy notice to continue.",
    }),
  })
  .refine((value) => value.password === value.confirm_password, {
    path: ["confirm_password"],
    message: "Passwords do not match.",
  });

export const forgotPasswordSchema = z.object({
  identifier: z.string().trim().min(1, "Enter your email or mobile number."),
});

export const resetPasswordSchema = z
  .object({
    uid: z.uuid("Enter the account reset identifier."),
    token: z.string().min(1, "Enter the reset token."),
    new_password: strongPassword,
    confirm_password: z.string(),
  })
  .refine((value) => value.new_password === value.confirm_password, {
    path: ["confirm_password"],
    message: "Passwords do not match.",
  });

export const profileSchema = z.object({
  first_name: z.string().trim().min(1, "Enter your first name.").max(150),
  last_name: z.string().trim().min(1, "Enter your last name.").max(150),
  email: z.email("Enter a valid email address.").or(z.literal("")),
  mobile_number: z.string().trim().nullable(),
});

export type LoginInput = z.infer<typeof loginSchema>;
export type RegistrationInput = z.infer<typeof registrationSchema>;
export type ForgotPasswordInput = z.infer<typeof forgotPasswordSchema>;
export type ResetPasswordInput = z.infer<typeof resetPasswordSchema>;
export type ProfileInput = z.infer<typeof profileSchema>;
