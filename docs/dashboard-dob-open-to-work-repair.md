# DOB and Open to Work repair — 6 September 2026

Scope: finish only the two identified failures and validation. All preceding working changes were preserved. The wider dashboard redesign is not claimed as complete.

## Exact causes and fixes

**DOB:** Krishna's ISO date `1995-08-15` passed serializer validation. `StaffProfileSerializer.update()` then called unrestricted `instance.full_clean()`, which rejected pre-existing empty `current_address`, `city` and `pin_code`. The unhandled Django ValidationError became HTTP 500. This was not a date format, timezone, age or permission failure.

Partial updates now exclude untouched model fields from field validation. Submitted fields still validate, including DOB bounds and explicitly submitted invalid PINs. Model validation failures become structured HTTP 400 responses. The update is atomic. No legacy blank field is filled with invented data.

**Open to Work:** the old service saved the flag, then accessed `profile.source_application` to record its audit event. Owner-created therapists such as Krishna have no application, so the reverse relation raised RelatedObjectDoesNotExist and returned HTTP 500 after the flag had already changed. The UI additionally always started at Off and replaced every error with an inaccurate activation warning.

The service now records the event against the existing PractitionerProfile, optionally retaining the source application when present. State and audit writes are atomic. Existing approval, activation, role and membership checks remain enforced. GET returns the persisted state; the UI loads it, disables duplicate submissions, uses the server response after saving and displays actual error messages.

## Migration

`practitioners.0005_profile_audit_support` was generated and applied successfully. It adds an optional profile relationship to the existing audit model and makes its application relationship optional, supporting Owner-created profiles without inventing applications.

To preserve all pre-existing partial model edits and maintain migration consistency, the same migration also includes the already-present optional PractitionerDocument.profile relationship, nullable document application relationship and PractitionerProfile.pending_credentials JSON field. These preparatory credential fields are not exposed as a completed credential workflow by this scoped repair. Existing rows and files are retained; no data rewrite or deletion is performed.

## Tests and checks

| Command/check | Final result |
|---|---|
| Backend `pytest tests/test_dashboard_repairs.py tests/test_practitioner_dob.py tests/test_practitioners.py tests/test_staff.py -q --no-cov` | **84 passed in 69.52s** |
| Frontend `pnpm test src/components/practitioners/dashboard-repairs.test.tsx src/components/practitioners/dob-profile.test.tsx src/components/practitioners/practitioners.test.tsx src/components/staff/staff-management.test.tsx` | **44 passed, 4 files**, 13.30s |
| `pnpm typecheck` | Passed |
| `python manage.py check` | No issues, 0 silenced |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `pnpm lint` | 0 errors, 6 existing warnings |
| `git diff --check` | Passed; line-ending conversion warnings only |
| `NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG=jeevasetu pnpm build` | Passed |

An initial backend run had 83 passes and one older fixture failure: it attempted Open to Work with an unusable password. That positive-path fixture now creates an activated applicant; a separate new test asserts unactivated accounts remain rejected. Frontend tests emitted existing jsdom scrollTo notices without failures.

New backend regression coverage includes blank legacy fields, DOB persistence and public-age consistency, invalid dates/age/PIN, Owner-created ON/OFF persistence without duplicate records, profile audit events, atomic rollback on audit failure, and ineligible accounts. New frontend coverage includes loading the actual state, both toggle directions, preserving state on failure, meaningful error messages and sending only ISO DOB in a partial update.

## Real-account verification

Using Krishna's existing account and actual endpoints inside a rolled-back transaction:

- DOB PATCH: HTTP 200; returned `1995-08-15`, age 31.
- Open to Work OFF: HTTP 200; subsequent GET returned false.
- Open to Work ON: HTTP 200; subsequent GET returned true.
- No PractitionerApplication existed or was created; both audit events linked to the existing profile.
- After rollback, Krishna's original DOB and work preference were confirmed unchanged.

No real password change, OTP send, fabricated DOB or activation repair was performed. This is API/database verification; a full interactive browser walkthrough was not performed in this narrowed continuation.

## Files for these fixes

- `backend/apps/staff/serializers.py`
- `backend/apps/practitioners/services.py`
- `backend/apps/practitioners/models.py`
- `backend/apps/practitioners/views.py`
- `backend/apps/practitioners/migrations/0005_profile_audit_support.py`
- `backend/tests/test_dashboard_repairs.py`
- `backend/tests/test_practitioners.py`
- `frontend/src/app/api/practitioners/open-to-work/route.ts`
- `frontend/src/components/practitioners/open-to-work.tsx`
- `frontend/src/components/practitioners/dashboard-repairs.test.tsx`
- This report. Other dirty files predate this scoped continuation.

No MSG91, customer authentication or authentication architecture changes. No commit or push.

## Docker restart and Redis recovery

The frontend/backend images rebuilt successfully. Startup initially failed because Redis was crash-looping on a malformed AOF tail; PostgreSQL recovered normally and became healthy. Redis's own checker found 33 corrupt bytes after 18,747,852 valid bytes. Before repair, the complete AOF directory was backed up to `/data/appendonlydir.backup-20260906-dashboard` in the existing Redis volume. With approval, `redis-check-aof --fix` truncated only that 33-byte tail and reported all AOF files and the manifest valid. No volume or PostgreSQL data was deleted. Frontend/backend were started and Celery services restarted following Redis recovery.

Final `docker compose ps`: frontend, backend, postgres, redis, celery-worker and celery-beat are all **healthy**. The restarted backend's Django check passes and `showmigrations practitioners` confirms 0005 applied.
