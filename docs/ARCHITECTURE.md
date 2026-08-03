# Architecture

## Goals and boundaries

The system supports discovery, booking, assignment, delivery, documentation, payment, and operational oversight of home physiotherapy services. It begins as a modular monolith so transactions, deployment, and development remain simple while domain boundaries stay explicit.

The browser communicates with Next.js for pages and static assets and with Django/DRF for application data. Next.js may provide rendering and frontend request mediation where needed, but it must not contain an independent business API or duplicate backend authorization. Django is the system of record and the sole business API.

```text
Browser / mobile web
        |
        +--> Next.js (UI, SSR, static assets)
        |
        +--> Django REST API
                 |-- PostgreSQL (system of record)
                 |-- Redis (cache, rate-limit support, Celery broker)
                 +-- Celery workers / scheduler (async and scheduled jobs)
```

## Proposed repository structure

```text
frontend/
├── src/
│   ├── app/                  # App Router routes and layouts
│   ├── components/           # Reusable accessible UI
│   ├── features/             # Domain-oriented UI and hooks
│   ├── lib/                  # API client, query, auth, utilities
│   ├── schemas/              # Zod schemas
│   ├── styles/
│   └── types/
├── public/
└── tests/                    # Unit, component, and browser tests

backend/
├── config/                   # Settings, URLs, ASGI/WSGI, Celery bootstrap
├── apps/
│   ├── accounts/
│   ├── patients/
│   ├── practitioners/
│   ├── services/
│   ├── availability/
│   ├── bookings/
│   ├── visits/
│   ├── clinical_records/
│   ├── payments/
│   ├── communications/
│   ├── operations/
│   └── audit/
├── common/                   # Shared primitives, exceptions, pagination
├── tests/                    # Cross-domain/integration tests
└── manage.py

infra/
├── docker/
├── nginx/                    # Added in production phase
└── deployment/               # AWS-compatible templates/configuration
```

## Module responsibilities

| Module | Responsibility |
|---|---|
| Accounts | Identity, authentication, role membership, consent state |
| Patients | Patient and caregiver profiles, addresses, preferences |
| Practitioners | Therapist profile, credentials, verification, service areas |
| Services | Service catalog, duration, pricing policy, eligibility |
| Availability | Working hours, leave, capacity, time-slot computation |
| Bookings | Requests, scheduling lifecycle, assignment, cancellation |
| Visits | Check-in/out, delivery status, operational visit evidence |
| Clinical records | Assessments, care plans, session notes, outcomes, attachments |
| Payments | Payment intents, invoices, refunds, immutable financial references |
| Communications | Templates, notification preferences, delivery records |
| Operations | Service zones, manual assignment, queues, escalation workflows |
| Audit | Security and sensitive-business event trail |

Modules may call stable service interfaces in-process. They must not reach into another module's internal query logic or create circular model dependencies. Cross-module side effects use application services plus `transaction.on_commit`; Celery handles slow or retryable work. Domain events may be introduced internally without implying microservices.

## Frontend page structure

```text
/(public)
├── /                         # Landing and service discovery
├── /services
├── /services/[slug]
├── /therapists               # Optional after business confirmation
├── /about
├── /contact
├── /privacy
└── /terms

/(auth)
├── /login
├── /register
├── /verify
└── /forgot-password

/(patient)
├── /dashboard
├── /book
├── /bookings/[id]
├── /care-plans/[id]
├── /profile
├── /addresses
└── /payments

/(practitioner)
├── /practitioner/dashboard
├── /practitioner/schedule
├── /practitioner/visits/[id]
├── /practitioner/patients/[id]
├── /practitioner/availability
└── /practitioner/profile

/(staff)
├── /ops/dashboard
├── /ops/bookings
├── /ops/assignments
├── /ops/practitioners
├── /ops/patients
├── /ops/payments
└── /admin                    # Django admin or restricted admin UI
```

Route guards improve UX only; DRF enforces every permission. Sensitive clinical details should not be placed in public URLs, analytics payloads, or cacheable page metadata.

## Roles and permissions

| Role | Principal permissions |
|---|---|
| Patient | Manage own profile/addresses; request and view own bookings; view permitted records; pay own invoices |
| Caregiver | Act for explicitly linked patients within granted scope; no implicit access from shared contact data |
| Physiotherapist | Manage own availability; view assigned patient minimum necessary data; update assigned visits and clinical notes |
| Dispatcher / operations | Manage scheduling and assignments; view operational patient data; no routine access to detailed clinical notes |
| Clinical supervisor | Review clinical records and care quality within assigned organization/scope |
| Finance staff | Manage invoices, reconciliation, and refunds; minimal clinical data |
| Support staff | Resolve account/booking issues through scoped support tools; sensitive access audited |
| Administrator | Configure platform and role assignments; elevated actions protected and audited |
| System worker | Narrow service identity for scheduled/async jobs; no interactive login |

Use Django groups/permissions plus object-level policy checks in domain services and DRF permission classes. Deny by default. Administrators are not automatically clinical superusers; break-glass access, if required, needs reason capture and audit.

## Key architecture decisions

- PostgreSQL owns transactional state; Redis is never the durable source of truth.
- UUID public identifiers prevent trivial enumeration; internal database design may use UUID primary keys consistently.
- Store timestamps in UTC and preserve the service location timezone for scheduling/display.
- Keep uploads in private object storage in production; store metadata and object keys in PostgreSQL.
- Use REST with an `/api/v1/` contract and OpenAPI documentation.
- Prefer idempotent commands, database constraints, and explicit state transitions for booking and payment workflows.
- Use third-party providers behind adapters so payment, SMS, email, maps, and storage vendors can change.

## Implemented infrastructure health contract

- `/api/v1/health/live/` verifies only that the Django process can serve requests; it has no downstream dependency.
- `/api/v1/health/ready/` reports aggregate PostgreSQL, Redis, and Celery configuration state with individual component routes for diagnosis.
- Dependency failures return HTTP 503 and only `ok` or `unavailable`; connection strings and exception details are never returned.
- Celery readiness validates application configuration. Worker process health is checked separately by the container runtime.
- Redis is the Celery broker but remains non-authoritative. Task results are disabled by default and require an explicit `CELERY_RESULT_BACKEND` justification/configuration.
- Celery Beat is wired with an empty schedule so scheduled business work can be added only in a later approved phase.

## Implemented tenancy foundation

- `accounts.User` is the minimal UUID-based custom identity model reserved before the first migration. Authentication flows and verification policy are not implemented.
- `Organization` is the tenant boundary. `Clinic` belongs to exactly one organization, and protected foreign keys prevent silent cascading deletion of tenant data.
- Organization membership establishes tenant access. A separate clinic membership mapping is implemented because future authorization must support users who may access only selected clinics within an organization.
- Development requests resolve organization context from `X-Organization-Slug`. Resolution is request-scoped, uses no global or thread-local state, and can later be replaced by a subdomain resolver.
- Middleware resolves context only. DRF permissions independently require an authenticated identity and active organization membership, while clinic querysets also require an active clinic mapping.
- Tenant-domain API querysets always start from the resolved organization. Controlled Django admin and migration code may use explicit unscoped model access.
- No superuser bypass is enabled. A future audited platform-administration policy requires separate approval and complete authorization tests.

## Load-handling strategy

1. Keep API instances stateless and scale Next.js, Django, and Celery independently.
2. Index frequent booking, practitioner, status, service-area, and time-window queries; inspect real query plans before adding indexes.
3. Apply pagination, bounded filters, serializer query optimization, connection pooling, and request timeouts.
4. Cache public catalog and safe derived data with short TTLs and explicit invalidation; never cache sensitive responses in shared caches.
5. Move notifications, exports, document processing, reconciliation, and retryable integrations to idempotent Celery tasks with exponential backoff and dead-letter visibility.
6. Protect scarce resources through atomic database transactions, unique/exclusion constraints where appropriate, and short-lived locks only when necessary.
7. Add rate limits at edge and application layers; use queues and admission controls during spikes.
8. Measure latency, error rate, saturation, queue depth, slow queries, and booking/payment success. Define SLOs before production launch.
9. Run representative load tests for search, slot lookup, booking submission, practitioner dashboards, and operational queues before each scale step.

## Testing strategy

- Backend unit tests: domain services, policies, state machines, calculations, and validators.
- Backend API/integration tests: serializers, permissions, transactions, PostgreSQL constraints, Celery task idempotency, and provider adapters.
- Frontend unit/component tests: Zod schemas, hooks, forms, error/loading states, keyboard operation, and accessibility checks.
- Contract tests: generated OpenAPI validation and frontend API-client compatibility.
- End-to-end tests: registration, booking, assignment, visit completion, cancellation/refund, and access-control boundaries.
- Security tests: authorization matrix, object ownership, upload validation, rate limiting, session/token handling, and dependency/static analysis.
- Performance tests: baseline and peak scenarios with recorded thresholds; verify no double booking under concurrency.
- CI quality gates: formatting, linting, type checks, tests, migration checks, dependency scanning, and production builds.
- Test data: synthetic only; factories must not copy production patient or clinical information.
