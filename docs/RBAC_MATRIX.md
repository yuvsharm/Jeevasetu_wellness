# RBAC Matrix

Phase 1E-A establishes authorization contracts and reusable server-side policy foundations. It does not expose role-management APIs or implement any business module.

| Role | Required scope | Current foundation | Future contract (not implemented) |
|---|---|---|---|
| Owner | Active organization membership; organization only | Tenant-wide role checks within its own organization | Organization administration and cross-clinic oversight |
| Manager | Active organization membership; optional active clinic membership | Organization or assigned-clinic role checks; cannot manage Owner roles | Delegated clinic operations excluding Owner-only powers |
| Physiotherapist | Active organization and clinic memberships | Assigned-clinic role checks | Assigned booking, patient, route, visit, and attendance work only; no finance, inventory, staff management, or global customer access |
| Customer | Active organization membership; self | Customer-role and explicit self/object-user checks | Own bookings, visits, payments, reports, and dashboard records only |

Booking, patient, route, visit, attendance, inventory, payment, report, and dashboard entries above are contracts only. No corresponding feature, model, API, page, or permission is implemented in Phase 1E-A.

## Invariants

- Authorization denies by default and never treats Django superuser status as an RBAC bypass.
- Middleware resolves organization context; DRF permissions and policies authorize it.
- Disabled users, memberships, assignments, organizations, or clinics cannot authorize.
- OWNER is organization scoped. PHYSIOTHERAPIST is clinic scoped. Clinic roles require a matching active clinic membership.
- The last active OWNER cannot be disabled or removed. A separately approved ownership-transfer mechanism must first establish another active organization-scoped OWNER.
- Normal role data accepts only OWNER, MANAGER, PHYSIOTHERAPIST, and CUSTOMER; no platform administrator role exists.
