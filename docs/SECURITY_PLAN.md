# Security Plan

## Security objectives

Protect patient, clinical, location, identity, and financial data against unauthorized access, alteration, loss, and disclosure. Apply least privilege, secure defaults, data minimization, traceability, and defense in depth. Final controls must be mapped to the laws and contractual requirements confirmed for the launch jurisdiction.

## Identity and access

- Use Django's custom user model and mature authentication primitives; use modern password hashing with tuned parameters.
- The Phase 1C custom-user schema is structural only. Tenant authorization currently denies by default unless the request has a resolved active organization and an active membership; clinic access additionally requires an active mapping.
- Tenant middleware supplies request context but grants no authority. DRF permissions and organization-scoped object queries enforce the boundary again, and unknown/inactive tenant responses do not reveal tenant existence.
- Platform superusers have no tenancy bypass. Any future bypass requires explicit policy, reason capture, audit events, and dedicated positive and negative tests.
- Phase 1D bearer authentication uses five-minute access tokens and rotating one-day refresh tokens. Refresh replay is blocked by the PostgreSQL-backed SimpleJWT outstanding/blacklist records; logout and password changes revoke refresh credentials.
- Login, registration, refresh, logout, password operations, and profile access have scoped throttles backed by a dedicated Redis logical database. Redis remains non-authoritative.
- Password-reset tokens are random, expire after 30 minutes, are stored only as SHA-256 digests, and are consumed once. Requests use non-enumerating responses, and no delivery provider is configured.
- Authentication audit events exclude raw identifiers, passwords, and tokens. Attempted identifiers are hashed; malformed forwarded IP data is discarded.
- Approved role constants and assignments are data-only. They grant no permissions and do not weaken tenant membership checks.
- Require verified contact before sensitive workflows. Add MFA for staff and administrators before production; strongly consider it for practitioners.
- Use short session/token lifetimes appropriate to role, secure rotation/revocation, logout invalidation, and reauthentication for sensitive changes.
- Cookies, if used, are `Secure`, `HttpOnly`, and appropriately `SameSite`; enforce CSRF protection. Never keep long-lived tokens in local storage.
- Centralize permission policies and test the full role/object matrix. Deny by default and prevent identifier-based access bypass.
- Separate platform administration, clinical supervision, operations, finance, and support access. Review privileged access periodically.
- Rate-limit login, verification, reset, slot search, booking, uploads, and public contact endpoints without creating unsafe patient lockouts.

## Data protection and privacy

- TLS in transit; encryption at rest for databases, backups, object storage, and managed caches where supported.
- Store secrets in a managed secret store, never source control, images, logs, or frontend bundles. Rotate on a defined schedule and after incidents.
- Collect only required data, label sensitive fields, and restrict serializers, exports, logs, analytics, and support views by purpose.
- Keep clinical documents private; short-lived signed access only after authorization. Validate type and size, randomize object keys, quarantine, and malware-scan uploads.
- Do not store raw payment card data. Use provider-hosted/tokenized flows and minimize PCI scope.
- Maintain versioned consent, privacy notice, retention, correction/export, deletion/anonymization, and legal-hold processes after legal review.
- Redact personal, clinical, authentication, and payment data from logs and exception traces.

## Application and infrastructure controls

- Validate all input at API boundaries and business-service boundaries; encode output and rely on framework protections against injection and XSS.
- Configure restrictive CORS, allowed hosts, trusted origins, CSP, HSTS, frame restrictions, MIME sniffing protection, and referrer policy.
- Disable debug and introspection exposure in production; return safe errors with correlation IDs.
- Pin dependencies through lockfiles, scan dependencies and images, generate an SBOM, and patch to defined severity SLAs.
- Use non-root, minimal containers; read-only filesystems where practical; separate runtime identities and network access by service.
- Keep PostgreSQL and Redis private. Require authentication/TLS as supported, enforce timeouts, backups, and least-privilege database roles.
- Verify webhook signatures, prevent replay, use idempotency, and treat all provider data as untrusted.
- Emit structured JSON logs with timestamp, severity, logger, and safe message fields. A defensive filter redacts password, OTP, token, secret, cookie, authorization, and API-key-like values before formatting.
- Keep request bodies, headers, cookies, authorization values, personal data, and clinical data out of routine logs. Exception logging records an exception type without serializing its message in the JSON formatter.
- Health responses expose only component names and `ok`/`unavailable` state. Dependency exception text, hosts, credentials, and connection URLs remain server-side.

## Audit, detection, and response

- Audit authentication, role changes, sensitive record access, clinical signing/amendment, booking overrides, refunds, exports, and break-glass actions.
- Make audit events append-only to ordinary users, time-synchronized, tamper-evident where required, and free of unnecessary sensitive payloads.
- Alert on repeated authentication failures, privilege changes, bulk record access/export, webhook anomalies, queue failures, and unusual refund activity.
- Maintain incident classification, contacts, containment, evidence preservation, notification, recovery, and retrospective runbooks.
- Test backup restoration and credential rotation. Define RPO/RTO and breach notification requirements before launch.

## Secure delivery gates

- Threat-model identity, caregiver delegation, booking concurrency, clinical records, payments, uploads, and support impersonation before implementation.
- Require code review, secret scanning, static analysis, dependency/image scanning, migration review, authorization tests, and production configuration validation in CI/CD.
- Conduct external penetration testing and privacy/security sign-off before production patient data is accepted.
- Use only synthetic test data outside production unless an explicitly approved, masked process exists.

## Decisions pending legal/business confirmation

- Applicable jurisdictional healthcare, privacy, tax, and electronic-record rules.
- Data residency, retention periods, age/minor consent, caregiver authority, and patient record access.
- Clinical signature/amendment requirements and break-glass policy.
- Exact authentication factors, identity proofing, GPS evidence, and payment/communication providers.
# Phase 1E-A authorization controls

All role checks require an enabled authenticated identity and active tenant chain. Cross-tenant actions, unsupported platform roles, manager-to-Owner escalation, self-broadening, and final-Owner removal are denied and audited with non-sensitive metadata. The final active Owner requires an approved transfer before disable/removal. Passwords, tokens, OTPs, authorization headers, clinical data, and confidential protocols are excluded from RBAC audit metadata.

## Phase 1E-B API-level controls

Access endpoints enforce JWT, the resolved tenant, active membership, active role, actor-level policy, and object scope independently. Querysets are restricted before UUID lookup; hidden same-tenant and cross-tenant objects return non-disclosing responses and generate safe escalation events. OWNER has organization-only authority. MANAGER may manage only PHYSIOTHERAPIST/CUSTOMER roles within delegated scope and cannot manage peers, Owners, or self. PHYSIOTHERAPIST/CUSTOMER writes are denied. Role removal is reasoned deactivation, the last active OWNER is transactionally protected, and immutable audits contain no credentials, headers, contact information, or business/clinical data.

## Phase 1F browser session controls

Access and refresh JWTs are held in HttpOnly, SameSite=Lax cookies and are Secure in production; they are never stored in localStorage/sessionStorage or returned by frontend session endpoints. Next.js performs same-origin checks for unsafe mediation requests, rotates refresh credentials server-side, clears cookies after revocation/failure, and maps backend failures to non-sensitive messages. Client role routing is explicitly UX-only. Missing/inactive tenant, membership, identity, or role state remains denied by Django and results in safe login/unauthorized states.

The initial development Owner is provisioned only through the local `bootstrap_jeevasetu_owner` Django management command. It requires a registered active identity, accepts no password, runs atomically, validates existing tenancy/RBAC models, and creates an immutable assignment audit event. No bootstrap HTTP endpoint or production startup hook exists.

Practitioner verification uploads accept only signature-matched PDF, JPEG, or PNG content up to 8 MB. Storage keys are private, downloads require applicant ownership or authorized Manager/Owner scope, and public profile responses exclude contact details, residential addresses, registration identifiers, documents, notes, availability calendars, workload, and patient information. Practitioner audit metadata uses a narrow allowlist and never stores document contents, government identifiers, credentials, tokens, or storage paths.
