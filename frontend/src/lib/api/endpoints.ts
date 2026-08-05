export const djangoEndpoints = {
  login: "/auth/login/",
  register: "/auth/register/",
  refresh: "/auth/refresh/",
  logout: "/auth/logout/",
  forgotPassword: "/auth/password/reset/request/",
  resetPassword: "/auth/password/reset/confirm/",
  profile: "/auth/profile/",
  access: "/access/me/",
} as const;

export const sessionEndpoints = {
  login: "/api/session/login",
  register: "/api/session/register",
  forgotPassword: "/api/session/forgot-password",
  resetPassword: "/api/session/reset-password",
  me: "/api/session/me",
  profile: "/api/session/profile",
  logout: "/api/session/logout",
} as const;
