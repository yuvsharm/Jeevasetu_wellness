# Practitioner DOB and homepage completion report

Verified 5 September 2026. No commit or push performed.

## Interruption and completion

The working tree was inspected and the existing Owner Physiotherapists / Therapist Availability cleanup was preserved. Its separate report is `docs/owner-physiotherapists-ui-review.md`. The DOB implementation already included the shared backend date rules, registration/approval propagation, shared frontend DOB controls, authorized editing, public age serialization, eligibility filtering and homepage carousel. These were continued rather than recreated.

The resumed work completed regression coverage and fixture corrections, prevented application submission while the latest review edits are still being saved, verified DOB edits retain mobile proof, ran the complete focused validation set and production build, rebuilt frontend/backend, and checked the live pages and existing DOB data.

## Final behavior

- Existing fields reused: `StaffProfile.date_of_birth` and `PractitionerApplication.date_of_birth`. Application DOB is the enrollment source before approval; the linked StaffProfile is authoritative after approval. The application retains its enrollment snapshot, while authorized response representations use the canonical current DOB. No stored age, duplicate model or DOB column was added.
- All new therapist creation/registration requires a valid date: not future, age 18 through 80 inclusive. Both paths use the shared backend validator. Incomplete application draft autosave remains possible; submission and approval enforce DOB. Existing legacy records remain usable, with missing DOB explicitly indicated privately and no fabricated public age.
- Age is calculated server-side against the clinic/organization local date, accounting for whether the birthday has occurred. February 29 birthdays advance on March 1 in non-leap years. Frontend review uses the backend preview endpoint instead of a second age formula.
- Owner Add Therapist, self-registration and application review expose DOB and derived age. Authorized profile editing uses the existing staff PATCH endpoints. Editing non-mobile details preserves verified-mobile proof; changing mobile invalidates it. MSG91/OTP architecture and password policy remain unchanged.
- Public cards disclose derived age only, never DOB. The public allowlist retains safe profile fields, real stored photo or initial fallback, experience, verified competencies, and moderated rating aggregate. Only approved ratings attached to completed appointments contribute; no ratings renders “No ratings yet.”
- Eligibility requires approved/public/open-to-work profile, matching active therapist account/role/memberships, staff/clinic/organization relationships, active clinic and organization, and approved source application when present. Approved active unavailability overlapping the current clinic-local day excludes a profile; future leave does not hide today's card. Detail/photo endpoints use the same eligibility.
- Badge is “Available with JeevaSetu.” No unsupported real-time “On Duty” claim was introduced.
- Homepage order is Therapies → Available Therapists → Plans & Offers. Existing carousel is reused with horizontal responsive scrolling, arrows and existing autoplay/pause behavior.

## Files changed for this feature

Backend:

- `backend/apps/accounts/serializers.py`, `views.py`
- `backend/apps/practitioners/dob.py` (new), `serializers.py`, `services.py`, `urls.py`, `views.py`
- `backend/apps/staff/serializers.py`
- `backend/tests/test_practitioner_dob.py` (new), `test_practitioner_auth.py`, `test_practitioners.py`, `test_staff.py`, `test_reviews.py`

Frontend:

- `frontend/src/app/page.tsx`
- `frontend/src/app/api/practitioners/dob-preview/route.ts` (new)
- `frontend/src/app/api/practitioners/public/[id]/photo/route.ts` (new)
- `frontend/src/components/auth/practitioner-auth.tsx`, `practitioner-auth.test.tsx`
- `frontend/src/components/practitioners/dob-field.tsx`, `dob-editor.tsx`, `dob-profile.test.tsx` (new)
- `frontend/src/components/practitioners/enrollment-form.tsx`, `manager-review.tsx`, `corrected-review.tsx`, `public-directory.tsx`, `practitioners.test.tsx`
- `frontend/src/components/staff/staff-creation-wizard.tsx`, `staff-management.tsx`, `staff-management.test.tsx`
- `frontend/src/components/availability/therapist-availability-page.tsx`
- `frontend/src/components/public/public-site.test.tsx`
- `frontend/src/lib/practitioners/contracts.ts`, `frontend/src/lib/staff/contracts.ts`
- This report.

Other uncommitted files belong to the preserved earlier Owner/availability work; they were not discarded or claimed as newly implemented here.

## Migrations and validation

No migration required or created. Existing nullable fields preserve legacy data.

| Check | Exact final result |
| --- | --- |
| Focused frontend | 9 files, 65 tests passed; 11.75 seconds; exit 0 |
| Focused backend | 109 tests passed; 106.18 seconds; exit 0 |
| TypeScript | Passed; exit 0 |
| ESLint | 0 errors, 6 existing warnings; exit 0 |
| Django system check | 0 issues; exit 0 |
| `makemigrations --check --dry-run` | No changes detected; exit 0 |
| `git diff --check` | Passed |
| Production Next.js build | Passed; 90 static pages generated; exit 0 |

Frontend focused files: `staff-management.test.tsx`, `therapist-availability-page.test.tsx`, `practitioner-auth.test.tsx`, `practitioners.test.tsx`, `manager-review.test.tsx`, `dob-profile.test.tsx`, `public-site.test.tsx`, `therapy-grid.test.tsx`, `booking-form.test.tsx`. Run using `pnpm test` with their `src/components/...` paths and `NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG=jeevasetu`.

Backend command: `docker compose exec -T backend pytest tests/test_staff.py tests/test_practitioners.py tests/test_practitioner_auth.py tests/test_practitioner_dob.py tests/test_practitioner_corrections.py tests/test_reviews.py tests/test_availability.py tests/test_assignment_workflow.py -q --no-cov`.

Non-failing output: existing jsdom scrollTo warnings, six existing lint warnings (unused test arguments and image lint), and existing build metadataBase warning. Initial test fixture/assertion failures were corrected before the final successful runs. A read-only manual query initially used the shorthand `dob` instead of existing `date_of_birth`; it was corrected and made no writes.

## Docker and browser verification

`docker compose up -d --build frontend backend` completed successfully. Final `docker compose ps` confirmed frontend, backend, PostgreSQL, Redis, celery-worker and celery-beat all healthy. The production build was verified separately; Compose retains its existing development-server configuration.

Live homepage inspected after rebuild: correct section order, Krishna's stored image, Asha's initial fallback, Asha age 34, no age for Krishna, exact availability badges, actual experience/competencies and “No ratings yet.” Screenshot inspection showed a clean horizontal card layout at the available browser viewport. Registration page exposes required Date of Birth and the 18–80/private helper text before Send OTP.

Owner workspace navigation loaded successfully, but the browser session ended during subsequent loading/compilation before the full live DOB editor walkthrough could be completed. No production OTP/account creation or DOB write was performed. Owner creation/edit and mobile-proof behavior were verified by focused automated tests. Separate mobile-device swipe and a full live authenticated save/reload walkthrough remain manual verification limitations.

## Existing data and remaining input

Final read-only database verification: Asha DOB is 1992-04-12; Krishna DOB is null. Both accounts are currently active and enabled. This final live reading supersedes the earlier observation that Asha was inactive. No account status or DOB was changed by this feature work.

Krishna requires the actual DOB from the Owner/therapist. It must be entered using the authorized editor; no age or DOB was invented. Existing future leave was preserved. No implementation work remains; the outstanding items are Krishna's real DOB and the stated manual verification limitations.
