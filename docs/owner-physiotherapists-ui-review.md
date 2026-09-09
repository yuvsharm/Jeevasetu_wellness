# Owner Physiotherapists UI cleanup — 5 September 2026

## Behavior and findings

1. Previous status: the table displayed `Available` only when the manually editable `StaffProfile.availability` flag equalled `AVAILABLE`. Both `BUSY` and `UNAVAILABLE` displayed `Unavailable`. This did not calculate current availability from working hours, bookings, leave, or `is_online`. Backend fields and therapist self-service flags remain unchanged.
2. Owner navigation and heading now say **Physiotherapists**. Manager filtering/management is removed from this directory; Manager roles and backend permissions remain. Columns are Professional, Role, Credentials, Schedule, Account, Actions. Schedule counts distinct approved active weekdays with non-expired schedules; it is not a real-time availability indicator. Account shows approval and active/inactive status separately.
3. Monday root cause: saved clinic operating hours return no Monday window for both Asha and Krishna. The clinic timezone is `Asia/Kolkata`. Thus 10:00–19:00 is invalid on Monday. Existing boundary comparisons use local wall-clock times, allow exact opening/closing boundaries, and correctly reject outside hours. No timezone comparison bug was found. The old API used `str(DjangoValidationError)`, producing Python list punctuation. It now returns the error messages directly. Closed Monday shows **Clinic is closed on Monday.** and Save is disabled; other outside-hours errors say **Therapist hours must remain within clinic operating hours.**
4. OFF → ON: Off days offer **Set Working Hours**. Saving creates an approved active working rule; opening/cancelling the editor does not save. Set Off deactivates the existing rule, retaining its history.
5. Editing uses a row immediately following the selected weekday. Monday's editor precedes Tuesday, and Tuesday's precedes Wednesday. Only one editor is open at a time. The dedicated View / Manage page includes photo, professional/contact summary, clinic timezone, account status, weekly schedule and leave.
6. New leave uses From Date, To Date and optional Reason, with Save and Cancel. The backend converts dates using the clinic timezone (organization fallback) to local midnight on From Date through exclusive midnight after To Date. Existing datetime APIs remain compatible. No migration is required. Existing records are not rewritten.
7. The main table shows the nearest/current approved active leave in red with both dates; additional entries use `+N upcoming`. Leave cards use clinic-local dates. The management page reads all result pages so historical records cannot hide active schedules or leave.
8. Photos: staff list and management use an authenticated, tenant-scoped photo endpoint. The shared source selector prefers the application profile photograph, then the staff photograph, and is also used by the public photo endpoint. It does not serialize private application photo/document storage URLs. Missing or failed images render the person's initial. Live read-only verification found no stored Asha photo (A fallback) and an existing Krishna photo file.
9. Activation/deactivation retains the existing role architecture. Inactive roles are excluded by assignment eligibility and public profile queries; records remain. Tests verify inactive assignment rejection and public photo disappearance/reappearance across deactivate/reactivate.
10. Data safety: Asha and Krishna remain present. Krishna's existing leave retains exactly its original timestamps, `2026-09-15 13:55 UTC` through `2026-09-16 15:05 UTC`, and active state. These were partial-day timestamps; the UI now displays their clinic-local dates as 15–16 September. New whole-day semantics are not retroactively applied to this record. No live schedule, identity, account or profile changes were performed.

## Verification

- Focused frontend: **43 passed** across staff management, therapist availability, shell navigation, appointments and booking form.
- Backend initial combined run: **54 passed** across staff, availability, assignment workflow, scheduling and practitioner operations.
- Final staff/availability run after adding photo and deactivation coverage: **33 passed**.
- Standalone TypeScript: passed. Production Next.js build (including TypeScript): passed.
- ESLint: passed, zero errors and six pre-existing warnings (unused test parameters and existing img elements).
- Build retains the existing metadataBase warning.
- Django system check: no issues. Migration consistency: no changes detected. No migrations added.
- `git diff --check`: passed.
- Docker frontend/backend rebuilt and restarted.
- Authenticated manual browser verification unavailable: the accessible browser redirects to `/login?reason=expired`. No credentials were changed or generated. Live read-only serializer checks verified the actual directory data and photo-file existence.
- MSG91, customer authentication, OTPs, booking/offer architecture and therapist registration architecture were not changed by this task.
- No commit and no push.

## Files edited or added by this task

Backend:

- `backend/apps/availability/serializers.py`
- `backend/apps/availability/services.py`
- `backend/apps/availability/views.py`
- `backend/apps/practitioners/views.py`
- `backend/apps/staff/photos.py` (new)
- `backend/apps/staff/serializers.py`
- `backend/apps/staff/urls.py`
- `backend/apps/staff/views.py`
- `backend/tests/test_availability.py`
- `backend/tests/test_staff.py`

Frontend:

- `frontend/src/app/api/staff/profiles/[id]/photo/route.ts` (new)
- `frontend/src/components/availability/therapist-availability-page.tsx`
- `frontend/src/components/availability/therapist-availability-page.test.tsx`
- `frontend/src/components/staff/profile-avatar.tsx` (new)
- `frontend/src/components/staff/staff-management.tsx`
- `frontend/src/components/staff/staff-management.test.tsx`
- `frontend/src/components/shell/app-shell.test.tsx`
- `frontend/src/lib/navigation/role-navigation.ts`
- `frontend/src/lib/staff/contracts.ts`

This report: `docs/owner-physiotherapists-ui-review.md`.

The workspace already contained uncommitted staff deletion, Owner route, availability route/page, and appointment test work. Those changes were preserved; the list above identifies files touched during this cleanup rather than claiming all existing git changes as new work.
