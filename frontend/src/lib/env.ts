import { z } from "zod";

const publicEnvironmentSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.url().default("http://localhost:8000/api/v1"),
  NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG: z
    .string()
    .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
    .default("jeevasetu"),
});

export const publicEnvironment = publicEnvironmentSchema.parse({
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
  NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG:
    process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG,
});
