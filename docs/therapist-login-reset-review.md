# Therapist login and password reset verification — 2026-09-05

## A–F. Krishna: cause, canonical state and login fix

The failure was mobile normalization before account lookup. The therapist form submitted `9286199103`; LoginSerializer previously accepted only an E.164 mobile for lookup. Normalization failed, leaving only the email lookup, and LoginView returned HTTP 401 `Invalid credentials.` before session or role processing. The frontend converted that into `The credentials or session are invalid.`

Before the fix, the same supplied password returned 401 with domestic input and 200 with `+919286199103`. `check_password()` for the supplied temporary password was **True**, verified again after rebuilding. No password or account data repair was necessary.

| Record | Verified state |
|---|---|
| User | `b28eb574-b283-46a4-8aec-51dea7a4866a`; `+919286199103`; `krishna1212@gmail.com`; active and enabled; usable password |
| Organization membership | `e49dc1fe-3efa-45aa-9920-ed59041a86fe`; active; organization `9a1276a7-aeab-4ac4-aa06-86b7202d8e3d`, slug `jeevasetu-wellness`, active |
| Clinic membership | `17519eb0-c56f-4086-8bf9-19fef80308a3`; active; clinic active |
| StaffProfile | `620dcd93-0768-42a1-9102-eecfe96cfef6`; PHYSIOTHERAPIST; qualification MPT; DOB missing; availability UNAVAILABLE. This model has no separate is_active field; account/membership/role controls access. Availability is a scheduling state. |
| PractitionerProfile | `2c0c2e13-76eb-4095-813a-1c81e11743c9`; approved, publicly visible, open to work; linked to the existing User and StaffProfile |
| RoleAssignment | `b7f19cfe-01b8-477a-8fe7-377355b89c39`; active PHYSIOTHERAPIST with organization/clinic scope |
| PractitionerApplication | None: Owner-created approved practitioner, not a pending self-applicant |

Krishna is eligible to sign in; Activate Account is not required for this already activated account. Missing DOB was not fabricated and does not explain the authentication failure.

Request path: `/therapist-login` → PractitionerLogin → `/api/session/login` → server-session login → Django `/api/v1/auth/login/` → LoginSerializer.find_user → User.check_password → JWT → `/access/me/` → session cookies → `/dashboard` role redirect to `/physiotherapist`. There was no custom authentication-backend defect, RBAC repair, activation bypass or redirect change.

The new login normalizer prefixes valid `[6-9]XXXXXXXXX` input with `+91`, while accepting existing canonical E.164 input. Strict stored identity normalization remains unchanged. Reset uses that same normalizer and restricts its mobile to valid Indian numbers. Login creates no identity/profile records. The therapist form shows the requested mobile helper and a clear invalid-credentials message.

Live verification after rebuilding: domestic input → BFF HTTP **200**, session cookie present, active PHYSIOTHERAPIST role; `/api/session/me` **200**; `/physiotherapist` **200**. Secrets, cookies, tokens and password hashes were not printed.

## G–J. Reset journeys

Previously, customer reset already used OTP. Staff/therapist Forgot Password used the legacy identifier/reset-token interface, which depended on obtaining a separate reset token; it was not a complete public mobile OTP journey. Legacy token endpoints remain compatible, while the public Forgot Password page now uses the existing mobile OTP infrastructure.

All three journeys now use registered 10-digit mobile → Send OTP → backend-verified OTP → shared New Password/Confirm Password component → reset success → explicit Sign in link to the appropriate login page:

| Context | Forgot page | Success Sign in destination |
|---|---|---|
| Therapist | `/forgot-password?context=therapist` | `/therapist-login` |
| Customer | `/customer-forgot-password` | `/customer-login` with existing returnTo retained |
| Owner/staff | `/forgot-password` | `/login` |

Success does not automatically log in or assign access. The shared password control retains the 8-character complexity checklist, show/hide controls, primary-password paste, and blocked confirmation paste/copy/cut. Mobile restart/resend clears the previous proof; changing identity requires fresh verification. Activate Account remains separate.

## K. Security

- Reuses existing OTP issue/verify endpoints, MSG91 widget integration and signed verification resolver. No MSG91 configuration/provider/template/captcha changes.
- Password step opens only after backend OTP verification. Final backend reset independently resolves the signed proof with a row lock, checks exact mobile, organization, verification ID, expiry and consumption state.
- Password update and proof consumption are atomic. Failed direct OTP attempts are outside that transaction so attempt counters persist.
- Django validates the password and uses set_password. Successful reset consumes the proof, invalidates outstanding legacy reset requests and blacklists existing refresh tokens. Existing access-token expiry behavior remains unchanged.
- Existing active/enabled staff accounts with a usable password and active organization membership are eligible; activation-pending, disabled and inactive accounts are rejected. Reset never changes account status or assigns roles. Applicants with no operational role can recover an existing account without gaining one.
- Customer login and customer role restrictions remain unchanged; legacy customer reset payloads remain accepted. Unknown/ineligible reset accounts return a generic error after verification.
- No duplicate models, accounts or profiles were introduced. No Asha/Krishna deletion, database reset, commit or push.

## L. Exact validation

| Check | Result |
|---|---|
| `pytest tests/test_therapist_login_reset.py tests/test_customer_password_auth.py tests/test_authentication.py tests/test_practitioner_auth.py -q --no-cov` in backend Docker | **55 passed in 66.39s** |
| `pnpm test src/components/auth src/lib/auth` | **10 files, 61 tests passed**, 9.85s |
| `pnpm typecheck` | Passed, exit 0 |
| `python manage.py check` | No issues, 0 silenced |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `pnpm lint` | 0 errors, 6 existing warnings: unused booking-test arguments and existing img usage |
| `git diff --check` | Passed; Git emitted line-ending conversion warnings only |
| `NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG=jeevasetu pnpm build` | Passed, all 94 static pages generated; existing metadataBase warnings |

New backend cases cover domestic/canonical therapist login, wrong password, no duplicate profiles, Owner/Manager/Physiotherapist reset, refresh revocation, old/new password authentication, proof replay, wrong mobile, expiry, weak/mismatched passwords, inactive/disabled/unactivated accounts, inactive roles, unknown accounts, and pending/rejected operational-access denial. Existing auth/customer suites cover wrong OTP, disabled login/refresh, customer isolation and reset. Frontend tests cover all three reset contexts, proof verification before password entry, helper/link behavior and the existing shared password rules/role routing.

Two issues found during checks were corrected: the new therapist test fixture needed clinic scope; the new forgot-password page needed Suspense around useSearchParams. The final suites/build above passed after those fixes. Initial sandbox-denied command attempts were rerun with permission.

No migration is needed for this auth fix. The prior practitioner migration and all earlier Owner/DOB/self-registration edits remain preserved.

## M. Docker

`docker compose up -d --build frontend backend` completed successfully. Final `compose ps`: frontend, backend, postgres, redis, celery-worker and celery-beat **healthy**. No data volumes were removed.

## N. Manual verification and remaining limits

1. Open `http://localhost:3000/therapist-login`, enter `9286199103` and the temporary password supplied in the request. Sign in; expected therapist dashboard is `/physiotherapist`.
2. Sign out, open Forgot Password, verify an OTP delivered to the registered mobile, enter a compliant new password and manually confirm it. After success, use Sign in; verify the old password fails and the new one works.
3. Repeat with existing authorized customer and Owner/staff test accounts from `/customer-login` and `/login`. Do not use a real account unless you intend to change its password.
4. Confirm mobile restart needs fresh OTP, expired/replayed proof fails, confirmation paste is blocked, and the correct login link is shown after success.

Browser inspection confirmed the rebuilt therapist login helper and all required links. The first attempt occurred during service restart and failed; a later navigation timed out during development compilation but the loaded page was subsequently inspected successfully. Login/session/dashboard were verified by real HTTP requests. Full interactive dashboard navigation and real SMS delivery/reset remain manual; no real OTP was sent and Krishna's password was not changed.

Krishna's missing DOB still requires his actual date from the user; no professional data was invented.

## Files changed for this login/reset task

- `backend/apps/accounts/validators.py`
- `backend/apps/accounts/serializers.py`
- `backend/apps/accounts/views.py`
- `backend/apps/accounts/urls.py`
- `backend/tests/test_therapist_login_reset.py` (new)
- `frontend/src/components/auth/practitioner-auth.tsx`
- `frontend/src/components/auth/practitioner-auth.test.tsx`
- `frontend/src/components/auth/customer-password-reset.tsx`
- `frontend/src/components/auth/customer-password-reset.test.tsx`
- `frontend/src/components/auth/account-password-reset.tsx` (new)
- `frontend/src/app/forgot-password/page.tsx`
- `frontend/src/app/api/session/account-password-reset/route.ts` (new)
- This report. Other dirty files belong to the preserved preceding tasks documented in the adjacent review reports.
