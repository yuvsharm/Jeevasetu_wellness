# Project Roadmap

Each phase ends with reviewed documentation, passing automated checks, and a clean Git milestone. Phase scope must not silently expand.

## Phase 0 — Architecture and decisions (current)

- Produce the seven planning documents.
- Confirm business workflows, clinical/privacy obligations, geography, payment model, and operational model.
- Exit: business questions resolved enough to define Phase 1 acceptance criteria.
- Suggested milestone: `docs: establish system architecture and delivery roadmap`.

## Phase 1 — Foundation and secure identity

Completed subphases:

- Phase 1A: repository and application foundation.
- Phase 1B: runtime-approved infrastructure, health, logging, OpenAPI, Celery, and container hardening.
- Phase 1C: organization/clinic schema, minimal migration-safe custom user, membership mappings, request-scoped tenant resolution, and deny-by-default tenancy permission/query foundations.
- Phase 1D: API-only JWT authentication, normalized registration/login identifiers, refresh rotation/blacklisting, logout, password/profile foundations, authentication audit/throttling, and non-authorizing role assignments.
- Phase 4B: Practitioner self-enrollment, secure evidence verification, scoped Manager review, transactional RBAC/staff activation, Open to Work eligibility, verified public directory, and non-authoritative booking preference.

OTP/contact verification, role permissions/RBAC enforcement, dashboards, consent, general audit foundations, and public/business features below remain future work.

- Initialize Git and repository conventions.
- Scaffold Next.js and Django/DRF only in their approved directories.
- Add PostgreSQL, Redis, Celery, and local Docker Compose.
- Establish environment configuration, health checks, structured logging, error format, OpenAPI generation, CI, and test harnesses.
- Implement custom user model before the first migration, authentication, email/phone verification policy, role groups, patient profile, practitioner profile skeleton, and basic protected dashboards.
- Add audit foundations, privacy/terms pages, consent capture, and baseline accessibility.
- Exit: locally reproducible stack; CI green; users can authenticate and access only their role-appropriate shell/profile.
- Suggested milestone: `feat: establish platform foundation and identity`.

## Phase 2 — Catalog, service areas, and practitioner onboarding

- Service catalog, duration and pricing rules.
- Practitioner credentials, approval workflow, skills, service areas, availability and leave.
- Operations screens for verification and catalog management.
- Exit: approved practitioners and valid service offerings can be configured without database edits.

## Phase 3 — Booking and assignment

- Patient addresses, service eligibility, slot search, booking lifecycle, manual/automatic assignment policy, notifications, rescheduling, and cancellation.
- Concurrency controls and end-to-end booking tests.
- Exit: an eligible patient can create a booking and operations can assign it without double booking.

## Phase 4 — Visit delivery and clinical workflow

- Check-in/out policy, assessments, care plans, progress/session notes, outcome measures, attachments, supervisor review, and audit controls.
- Exit: a therapist can safely document an assigned visit and the patient can see the approved subset.

## Phase 5 — Payments and communications

- Provider-hosted payment flow, invoices/receipts, webhook processing, reconciliation, refunds, reminder schedules, and delivery tracking.
- Exit: payments are idempotent, auditable, reconciled, and tested against provider sandbox behavior.

## Phase 6 — Production readiness and launch

- Staging, production IaC, private storage, secrets management, Nginx/load balancer, monitoring, alerting, backups, recovery drill, vulnerability remediation, load testing, and operational runbooks.
- Exit: security review, accessibility review, backup restore, rollback, and launch checklist approved.

## Phase 7 — Post-launch evolution

- Analytics using de-identified/minimized events, waitlists, packages/subscriptions, referral workflows, mobile/PWA improvements, and additional regions.
- Split services only after measured scaling or organizational constraints justify the operational cost.

## Cross-cutting definition of done

- Acceptance criteria and role permissions are documented.
- Tests cover happy paths, failure paths, and authorization boundaries.
- Migrations are reversible or have an explicit rollback/data migration plan.
- Security, accessibility, observability, and privacy impacts are reviewed.
- Documentation and API schema match behavior.
- No secrets or real patient data enter source control, fixtures, logs, or screenshots.

## Business confirmations required

1. Initial launch geography, supported timezones/languages, and service radius rules.
2. Whether the platform serves adults only, minors, dependents, and/or caregiver-managed accounts.
3. Legal entity and applicable healthcare/privacy rules, retention periods, consent wording, and data residency.
4. Marketplace versus employed/contracted therapist model, credential types, and verification ownership.
5. Booking model: instant, request-and-confirm, operations-assigned, recurring packages, and emergency exclusions.
6. Pricing: fixed, distance-based, practitioner-specific, taxes, discounts, packages, cancellation/no-show fees.
7. Payment provider, payment timing, cash support, therapist payouts, invoices, and refund authority.
8. Clinical documentation requirements, outcome measures, signatures, amendment rules, and patient-visible fields.
9. Location/check-in evidence requirements and explicit consent for GPS or background location.
10. Communication channels/providers, transactional consent, reminder timing, and marketing opt-in policy.
11. Support hours, escalation rules, SLAs/SLOs, expected launch and peak volume, and business continuity targets.
12. Whether patients may choose a named therapist or only preferences such as gender/language/specialty.
# Phase 1E-A: RBAC foundation

Implemented as a backend foundation: four tenant-aware roles, membership/clinic scope validation, deny-by-default policy utilities, escalation protection, immutable audit events, migration, and focused tests. Role-management APIs, UI, dashboards, and every business-domain module remain future work and are not part of this phase.

## Phase 1E-B: RBAC management APIs

Implemented as an API-only authorization layer: current-access summary, scoped role listing/detail, controlled assignment and clinic-scope correction, audited activation/deactivation, Owner/Manager boundaries, safe OpenAPI contracts, and regression tests. Frontend UI, dashboards, public/business APIs, and all business-domain modules remain future work.

## Phase 1F: authenticated dashboard shells

Implemented frontend foundation: login/registration/password-reset forms, HttpOnly server-mediated sessions, protected routes, deterministic backend-confirmed role redirects, responsive shared navigation, profile editing, and four placeholder-only dashboard shells. Logo/public branding, OTP, tenant discovery, and every operational/business module remain future work.
