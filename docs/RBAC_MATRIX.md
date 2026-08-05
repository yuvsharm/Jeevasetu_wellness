# RBAC Matrix

Phase 1E-A established authorization contracts and reusable server-side policy foundations. Phase 1E-B exposes only the secured role-management API described below; it implements no business module.

| Role | Required scope | Implemented access API | Future contract (not implemented) |
|---|---|---|---|
| Owner | Active organization membership; organization only | View all assignments in own organization; assign four approved roles; correct scope; activate/deactivate subject to final-Owner safeguard | Organization administration and cross-clinic oversight |
| Manager | Active organization membership; optional active clinic membership | View/manage PHYSIOTHERAPIST and CUSTOMER only within delegated scope; no Owner/Manager management, self-promotion, or scope broadening | Delegated clinic operations excluding Owner-only powers |
| Physiotherapist | Active organization and clinic memberships | Own active summary/assignments only; no role writes | Assigned booking, patient, route, visit, and attendance work only; no finance, inventory, staff management, or global customer access |
| Customer | Active organization membership; self | Own active summary/assignments only; no role writes | Own bookings, visits, payments, reports, and dashboard records only |

Booking, patient, route, visit, attendance, inventory, payment, report, and dashboard entries above are contracts only. No corresponding feature, model, API, page, or permission is implemented in Phase 1E-A.

## Invariants

- Authorization denies by default and never treats Django superuser status as an RBAC bypass.
- Middleware resolves organization context; DRF permissions and policies authorize it.
- Disabled users, memberships, assignments, organizations, or clinics cannot authorize.
- OWNER is organization scoped. PHYSIOTHERAPIST is clinic scoped. Clinic roles require a matching active clinic membership.
- The last active OWNER cannot be disabled or removed. A separately approved ownership-transfer mechanism must first establish another active organization-scoped OWNER.
- Normal role data accepts only OWNER, MANAGER, PHYSIOTHERAPIST, and CUSTOMER; no platform administrator role exists.
- Normal removal uses audited deactivation rather than DELETE. No public audit API exists.
