# API Plan

## Contract conventions

- Base path: `/api/v1/`.
- JSON over HTTPS; UTF-8; ISO 8601 timestamps with offsets; ISO currency codes.
- OpenAPI schema generated from DRF and checked in CI for breaking changes.
- Consistent error envelope with stable machine code, human-safe message, field errors, and correlation ID.
- Cursor pagination for high-growth timelines/queues; page pagination may be used for bounded admin lists.
- Filtering and ordering are explicit allowlists; no arbitrary field exposure.
- Unsafe retryable commands accept an `Idempotency-Key`, especially booking, payment, refund, and webhook-related operations.
- Optimistic concurrency/version checks are used where simultaneous edits can lose data.

## Endpoint structure

The list is a resource map, not a final contract. Actions are used only for genuine state transitions.

```text
/api/v1/health/live
/api/v1/health/ready

/api/v1/tenancy/context              # Phase 1C isolation probe
/api/v1/tenancy/clinics              # Active mapped clinics only
/api/v1/tenancy/clinics/{id}         # Tenant- and clinic-scoped lookup

/api/v1/auth/register
/api/v1/auth/login
/api/v1/auth/logout
/api/v1/auth/refresh                 # If token architecture is selected
/api/v1/auth/verify
/api/v1/auth/password/reset
/api/v1/auth/me

/api/v1/patients/me
/api/v1/patients/{patient_id}        # Scoped caregiver/staff access
/api/v1/patients/{patient_id}/caregivers
/api/v1/addresses
/api/v1/consents

/api/v1/practitioners
/api/v1/practitioners/{id}
/api/v1/practitioners/me
/api/v1/practitioners/me/credentials
/api/v1/practitioners/me/availability
/api/v1/practitioners/me/availability/exceptions

/api/v1/services
/api/v1/services/{slug}
/api/v1/service-zones/eligibility
/api/v1/availability/slots

/api/v1/bookings
/api/v1/bookings/{id}
/api/v1/bookings/{id}/confirm
/api/v1/bookings/{id}/reschedule
/api/v1/bookings/{id}/cancel
/api/v1/bookings/{id}/assign          # Operations only

/api/v1/visits
/api/v1/visits/{id}
/api/v1/visits/{id}/check-in
/api/v1/visits/{id}/check-out
/api/v1/visits/{id}/complete

/api/v1/clinical-episodes
/api/v1/clinical-episodes/{id}
/api/v1/clinical-episodes/{id}/assessments
/api/v1/clinical-episodes/{id}/care-plans
/api/v1/visits/{id}/session-notes
/api/v1/clinical-records/{id}/amendments
/api/v1/clinical-attachments

/api/v1/payments
/api/v1/payments/{id}
/api/v1/invoices
/api/v1/refunds
/api/v1/webhooks/payments/{provider}

/api/v1/notifications
/api/v1/communication-preferences

/api/v1/ops/bookings
/api/v1/ops/assignment-queue
/api/v1/ops/practitioner-verifications
/api/v1/ops/audit-events             # Highly restricted
```

## State transitions

Exact states require workflow confirmation. A safe initial model is:

```text
Booking: requested -> confirmed -> assigned -> in_progress -> completed
                     \-> cancelled
                     \-> expired

Payment: created -> pending -> authorized/captured -> refunded/partially_refunded
                    \-> failed/cancelled

Clinical note: draft -> signed -> amended (append-only correction)
```

Transitions are server-controlled, permission-checked, validated against current state, and audited. Clients must not set arbitrary status fields.

## Authentication and authorization

Select same-site secure cookie sessions or short-lived tokens with rotated refresh credentials based on hosting topology. Do not store long-lived bearer credentials in browser local storage. CSRF protection is mandatory for cookie-authenticated unsafe requests. Every endpoint applies role, scope, ownership/assignment, record state, and minimum-necessary field rules.

Phase 1C tenancy probes resolve `X-Organization-Slug` and require an authenticated `request.user`, active organization membership, and—where a clinic object is involved—an active clinic mapping. Missing context is rejected, while malformed, unknown, and inactive organization identifiers share a non-disclosing unavailable response. Middleware resolution is never sufficient authorization. No superuser bypass or role-specific RBAC is active.

## Integration boundaries

- Payment provider webhooks: signature verified against raw body, timestamp/replay checked, event deduplicated, processing acknowledged quickly and completed asynchronously.
- Email/SMS: template IDs and business data sent through an adapter; delivery callbacks are authenticated and deduplicated.
- Maps/geocoding: addresses minimized, provider terms reviewed, results cached only as policy permits.
- Object storage: server issues short-lived upload/download grants after permission and file policy checks; malware scanning/quarantine precedes availability.

## API evolution

Additive changes are preferred within `v1`. Deprecations are measured, communicated, and time-bounded. Breaking semantic or representation changes require a versioning decision. The frontend must consume a typed client generated from or validated against the OpenAPI contract, without duplicating server rules as authority.
