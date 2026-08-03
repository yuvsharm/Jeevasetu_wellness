# Database Plan

## Conventions

- PostgreSQL is authoritative. Use Django migrations from the first implementation phase.
- Create a custom user model before the initial migration.
- Prefer UUID identifiers, timezone-aware timestamps, explicit status enums, database constraints, and soft deactivation over silent deletion where records have clinical or financial significance.
- Every sensitive entity carries appropriate created/updated metadata; critical records also record actor and reason through audit events or version history.
- Encrypt connections and storage. Highly sensitive application fields may need field-level encryption after regulatory review.
- Avoid generic foreign keys for core business records; keep relationships explicit.
- Separate operational visit facts from clinical content to enforce least privilege.

## Entity inventory

### Identity and organization

- `User` (implemented foundation): UUID primary key with Django's standard identity structure; no login, verification, OTP, JWT, or reset flow yet.
- `Organization` (implemented): UUID primary key, legal/display names, globally unique slug, active state, optional timezone/default currency, and timestamps.
- `Clinic` (implemented): protected organization relationship, organization-scoped unique slug, active state, optional address placeholders/timezone, and timestamps.
- `OrganizationMembership` (implemented): protected user and organization relationships, active/disabled state, timestamps, and one mapping per user/organization.
- `ClinicMembership` (implemented): protected organization-membership and clinic relationships, active/disabled state, timestamps, and one mapping per membership/clinic. Model validation rejects mappings across organizations.
- `RoleMembership`: user-to-role assignment, optional organization/scope, validity period.
- `ConsentRecord`: versioned consent/policy acceptance, purpose, timestamp, evidence.
- `AuthSession` or token metadata: only if required by the selected authentication design.

### Patients and relationships

- `PatientProfile`: demographics and safe care-relevant preferences linked to a user or managed account.
- `CaregiverLink`: caregiver-patient relationship, permission scope, verification/status, validity.
- `Address`: structured private service address, coordinates/zone reference where permitted.
- `EmergencyContact`: scoped patient contact details.
- `PatientPreference`: therapist gender/language and scheduling preferences; only confirmed requirements.

### Practitioners and catalog

- `PractitionerProfile`: professional identity, biography, operating status.
- `Credential`: registration/license type, issuer, identifier, validity, verification status.
- `PractitionerSkill`: mapping to service/specialty with proficiency/approval metadata.
- `Service`: public catalog entry.
- `ServiceVariant`: duration, delivery type, eligibility and base pricing reference.
- `ServiceZone`: supported geography and operational rules.
- `PractitionerZone`: practitioner coverage mapping.
- `AvailabilityRule`: recurring working pattern.
- `AvailabilityException`: leave, override, block, or additional capacity.

### Booking and delivery

- `Booking`: patient, requested service, address snapshot/reference, requested time, status, source.
- `BookingStatusHistory`: immutable state changes with actor, reason, and timestamp.
- `Assignment`: practitioner assignment history, status, actor, reason.
- `Visit`: scheduled delivery occurrence, timing, operational state.
- `VisitCheckEvent`: check-in/out evidence and permitted location metadata.
- `Cancellation`: party, reason, policy outcome, fees.
- `RecurringPlan`: optional booking-series intent; included only if confirmed.

### Clinical records

- `ClinicalEpisode`: care episode linking patient, service, responsible clinician, status.
- `Assessment`: versioned structured assessment and clinician attribution.
- `CarePlan`: goals, planned frequency/duration, approval and review state.
- `CarePlanGoal`: measurable goal and status.
- `SessionNote`: visit-linked clinical note, version, author, signed/locked status.
- `OutcomeMeasure`: instrument, score/value, units and observed date.
- `ClinicalAttachment`: private object metadata, category, integrity/security scan state.
- `RecordAmendment`: append-only correction reason and relationship to superseded content.

### Finance and communications

- `PriceSnapshot`: booking-time monetary breakdown and currency.
- `Payment`: provider-neutral payment state and idempotency reference; no raw card data.
- `PaymentAttempt`: provider request/result metadata.
- `Invoice`: numbered financial document and immutable totals.
- `Refund`: payment-linked amount, reason, state, approver.
- `PractitionerPayout`: optional, pending contractor model confirmation.
- `Notification`: recipient, channel, template/version, business reference, state.
- `NotificationAttempt`: delivery provider result and retry metadata.
- `CommunicationPreference`: transactional/marketing permissions by channel and purpose.

### Governance and operations

- `AuditEvent`: actor, action, target, timestamp, request/correlation ID, outcome, safe metadata.
- `AccessEvent`: sensitive-record access where required by regulation.
- `SupportCase`: issue, ownership, status, resolution references.
- `FeatureFlag`: optional operational rollout control; secrets never stored here.
- `OutboxEvent`: durable post-commit event for reliable async side effects if required.

## Relationship and integrity rules

- Tenant slugs are lowercase development-safe identifiers. Organization slugs are global; clinic slugs are unique only within an organization.
- Tenant relationships use `PROTECT`; organization, clinic, membership, and user deletion cannot silently cascade through tenant data.
- Tenant and clinic authorization uses active membership mappings and organization-scoped queries. Deactivation is preferred over deletion.

- A booking belongs to one patient and service variant and has one active requested schedule at a time.
- Assignment history is retained; only one active practitioner assignment per visit.
- Practitioner availability, leave, and existing visits must be checked atomically when assigning.
- Clinical records require an authorized clinical episode/visit relationship and retain authorship/version history.
- Monetary values use decimal minor-unit-safe handling and explicit ISO currency; booking prices are snapshotted.
- Provider webhooks are unique by provider event ID and processed idempotently.
- Caregiver access is modeled explicitly and can be revoked without altering patient ownership.
- Audit records are append-only to application users and must omit secrets and unnecessary clinical content.

## Index and retention outline

Candidate composite indexes include booking status/time, practitioner/time, patient/created time, visit/assignment state, notification state/schedule, payment provider reference, and active credential expiry. Final indexes must follow observed query plans.

Retention and deletion must be policy-driven per data category. Account closure may deactivate access while legally retained clinical, audit, and financial records remain restricted. Define anonymization, legal holds, export, correction, and deletion workflows only after legal confirmation.
