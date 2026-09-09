# Therapist self-registration completion and gap analysis

Verified 5 September 2026. No commit or push.

## Work preserved and completed

Before the latest continuation, the working tree already contained the previous Owner availability/photo cleanup and DOB/homepage feature. The current journey work had also introduced the shared wizard's self-application mode, recruitment page, complete-submission endpoint, public form options, and additive application migration. Migration 0004 had already been applied locally. These edits were inspected and preserved, not recreated.

The continuation fixed multipart upload parsing, completed reviewer photo/competency/schedule display, added the private photo proxy route, completed correction/resubmission handling for new applications, tightened required-photo/document checks, corrected the self-submission button and success state, verified exact-mobile proof binding and canonical identity creation, and completed validation/build/Docker work.

## Final journey

1. Details: name, email, exact +91 mobile, gender, DOB, qualification, Years.Months experience, clinic, languages, required photograph, practitioner type, specialization, canonical therapy competencies, canonical service areas, working days/hours and bio.
2. Verify Mobile: duplicate check before issuing OTP; existing booking verification and MSG91 widget functions are reused.
3. Password: existing shared PasswordCreationFields, minimum eight characters with uppercase/lowercase/number/special character, show/hide, live checklist and confirmation protections.
4. Documents: Government Identity Proof and Qualification Certificate required; Experience and Other Practitioner Certificate optional. PDF only, maximum 25 MB each, including backend file-signature validation. Replace/remove and filename/preview controls remain available.
5. Review: photograph, private DOB and derived age, all personal/professional/schedule values and document filenames. Edit Details, Edit Password and Edit Documents preserve other wizard state and return to Review. Non-mobile edits retain verification; changing mobile clears proof and requires fresh OTP.
6. Submit Application: backend independently validates fields, uploads, scoped catalog selections and the exact mobile verification token. Account, organization membership, application, pending competencies and private documents are written atomically. No operational staff profile, practitioner profile or role is created.
7. Pending Approval: stored lifecycle status remains existing `SUBMITTED` (or `RESUBMITTED` after correction); user-facing status is Pending Approval. Applicant may sign in to check status. Owner review, document and competency verification, approval/rejection/correction use the existing architecture.

On approval, one StaffProfile and PractitionerProfile are linked to the existing applicant, with the exact qualification, DOB, canonical service areas/competencies and working schedule. Repeated approval is idempotent. Existing public/Open to Work eligibility remains in force.

## Owner versus self-applicant gap analysis

| Area | Comparison | Intentional difference? |
| --- | --- | --- |
| Initial form and steps | Both render the same StaffCreationWizard, including photo, DOB, experience, language normalization, password, PDFs and review edits | No field/step fork |
| Mobile verification | Same issue/verify functions and signed proof; self preflight exposes the existing availability behavior through a throttled public endpoint | Yes: applicants are not signed in yet |
| Professional options | Same active TherapyOption and ServiceArea records, scoped to organization | No data-source difference |
| Administrative controls | Owner retains Active, Public Profile Visible and Joining Date; self-applicant cannot set operational/public access | Yes: Owner-only lifecycle controls |
| Final action | Owner creates a staff profile using its existing workflow; self uses Submit Application | Yes: requested lifecycle distinction |
| Initial identity | Self creates one account and one submitted application, with no staff role/profile; Owner retains direct staff creation | Yes |
| Qualifications | Self retains exact text alongside the existing legacy qualification category; approval copies exact text into StaffProfile | Yes: preserves older applications while matching Owner free-text qualification |
| Schedule persistence | Owner keeps its existing immediate availability workflow; self schedule stays on application until approval | Yes: no preapproval operational availability |
| After submission | New self applications use a professional correction screen and private document controls; account password changes use existing account recovery after creation, and verified account mobile cannot be changed through an application PATCH | Yes: pre-submit Edit Password/mobile re-verification remain in the shared wizard; post-account identity is protected |
| Existing applications | Older saved applications retain their existing enrollment data and editing path; the new registration UI does not send applicants through that old flow | Yes: backward compatibility, no invented backfill |
| Legacy registration API | Existing account/activation compatibility endpoints remain; the new self-registration UI submits the full multipart application endpoint | Yes: existing activation/auth compatibility retained |

No remaining known implementation gap in the requested new-registration sequence. Live SMS and a complete authenticated browser submission/approval walkthrough remain unverified.

## Migration and existing data

Created/applied `backend/apps/practitioners/migrations/0004_practitionerapplication_qualification_title_and_more.py`:

- Exact `qualification_title` text, blank for existing rows.
- `service_areas` relation to existing ServiceArea records.
- `working_days` list, initially empty on existing applications.
- Nullable `working_hours_start` and `working_hours_end`.

Only additive fields/relations; no new therapist model, age column, destructive migration or inferred professional-data backfill. Final showmigrations marks 0001–0004 applied. Read-only final verification: Asha DOB remains 1992-04-12; Krishna DOB remains null. Neither therapist was deleted or edited by this task. Krishna's actual DOB still requires authorized input.

## Feature-specific files changed

Backend:

- `backend/apps/practitioners/models.py`
- `backend/apps/practitioners/migrations/0004_practitionerapplication_qualification_title_and_more.py` (new)
- `backend/apps/practitioners/registration.py` (new)
- `backend/apps/practitioners/serializers.py`
- `backend/apps/practitioners/services.py`
- `backend/apps/practitioners/urls.py`
- `backend/apps/staff/serializers.py`
- `backend/tests/test_complete_application.py` (new)

Frontend:

- `frontend/src/app/work-with-us/page.tsx`
- `frontend/src/app/therapist-register/page.tsx`
- `frontend/src/app/api/practitioners/registration-options/route.ts` (new)
- `frontend/src/app/api/practitioners/mobile-availability/route.ts` (new)
- `frontend/src/app/api/practitioners/register-complete/route.ts` (new)
- `frontend/src/app/api/practitioners/applications/[id]/profile-photo/route.ts` (new)
- `frontend/src/components/staff/staff-creation-wizard.tsx`
- `frontend/src/components/staff/staff-management.test.tsx`
- `frontend/src/components/auth/practitioner-auth.tsx`
- `frontend/src/components/auth/practitioner-auth.test.tsx`
- `frontend/src/components/practitioners/self-registration.tsx` (new)
- `frontend/src/components/practitioners/self-registration.test.tsx` (new)
- `frontend/src/components/practitioners/recruitment-page.tsx` (new)
- `frontend/src/components/practitioners/application-professional-summary.tsx` (new)
- `frontend/src/components/practitioners/corrected-review.tsx`
- `frontend/src/components/practitioners/manager-review.tsx`
- `frontend/src/components/practitioners/enrollment-form.tsx`
- `frontend/src/components/practitioners/dob-profile.test.tsx`
- `frontend/src/lib/practitioners/contracts.ts`
- This report.

Other dirty/untracked files predate this journey and remain preserved. Temporary implementation scripts were removed.

## Exact validation results

| Check | Final result |
| --- | --- |
| Focused frontend suite | 13 files, 92 tests passed; 14.31 seconds; exit 0 |
| Focused backend suite | 72 tests passed; 61.98 seconds; exit 0 |
| Final complete-application tests, including two added proof/correction cases | 10 passed; 19.94 seconds; exit 0. Eight overlap the 72-test suite: 74 distinct backend tests total |
| TypeScript | Passed; exit 0; also passed in final build |
| Django system check | No issues (0 silenced) |
| Migration consistency | No changes detected |
| ESLint | 0 errors, 6 existing warnings; exit 0 |
| git diff --check | Passed; informational line-ending warnings only |
| Production Next.js build | Passed; compilation 7.0 seconds, TypeScript 11.8 seconds, 93 static pages; exit 0 |

Frontend command: `pnpm test src/components/practitioners/self-registration.test.tsx src/components/staff/staff-management.test.tsx src/components/auth src/components/practitioners/dob-profile.test.tsx src/components/practitioners/practitioners.test.tsx src/components/practitioners/manager-review.test.tsx src/components/public/public-site.test.tsx src/components/appointments/booking-form.test.tsx`, with `NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG=jeevasetu`.

Backend command: `docker compose exec -T backend pytest tests/test_complete_application.py tests/test_practitioner_auth.py tests/test_practitioners.py tests/test_practitioner_corrections.py tests/test_staff.py tests/test_customer_registration.py tests/test_reviews.py -q --no-cov`. Final added cases rerun serially with `pytest tests/test_complete_application.py -q --no-cov`.

Intermediate failures were resolved: missing multipart parser, obsolete self-registration assertions, disabled Documents button/final self label, and test mock typing. An overlapping backend test invocation collided on the test database; it was rerun successfully after the first run ended. No live database cleanup was performed. Existing non-failing output includes jsdom scrollTo, six lint warnings, and metadataBase build warnings.

## Docker and manual verification

`docker compose up -d --build frontend backend` succeeded. Final `docker compose ps`: frontend, backend, PostgreSQL, Redis, celery-worker and celery-beat all healthy. Existing development-server Compose configuration remains; production build was checked independently.

After rebuild, inspected recruitment page content and screenshot: balanced two-column hero, professional preview, benefit cards, ten-step journey and correct CTA destinations. Inspected full registration form with live clinic, therapies and service-area options, required DOB/photo, clear +91 helper, schedule and five-step progress. No fake production account or professional data was submitted.

Login was inspected before rebuild as a normal mobile/password form; automated tests verify the new Apply to Join link and Sign In label. Browser timeouts interrupted final login/Owner inspection, so final live login labeling, Owner photo/review actions, mobile-width walkthrough, and end-to-end authenticated submission/approval remain manual verification items. Automated tests cover pre-submit edits, proof retention/invalidation, pending lifecycle, Owner regression and approval idempotency.

Real OTP/SMS was not exercised. Tests used the existing disabled-provider test mode and mocks; MSG91 configuration/architecture was not modified. Customer auth and booking/offers implementation were not changed in this journey.
