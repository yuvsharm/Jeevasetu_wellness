# Jeevasetu Wellness

Jeevasetu Wellness is a planned physiotherapy home-service platform connecting patients, caregivers, physiotherapists, operations staff, and administrators.

## Current status

Phase 1D adds the API-only identity and authentication foundation on top of the approved tenancy infrastructure. It includes normalized registration, email/mobile login, short-lived JWT access tokens, rotating refresh tokens with blacklisting, logout, password change/reset foundations, profile maintenance, authentication throttling/audit events, and role constants/assignments that grant no permissions. Business-domain modules and frontend business pages remain deferred.

The custom Django user model must be introduced during the authentication phase before the first production migration.

## Approved architecture

- Frontend: Next.js (latest stable at implementation time), TypeScript, Tailwind CSS, React Hook Form, Zod, and TanStack Query.
- Backend: Python, Django, Django REST Framework, PostgreSQL, Redis, and Celery.
- Runtime boundary: Django/DRF is the only backend API. Node.js is limited to Next.js runtime and frontend tooling.
- Application shape: modular monolith with clear Django domain modules; no microservices initially.
- Infrastructure: Docker Compose for local and staging foundations, GitHub Actions for CI/CD, an AWS-compatible production target, and Nginx at the production edge later.

## Planning documents

- [Architecture](docs/ARCHITECTURE.md)
- [Project roadmap](docs/PROJECT_ROADMAP.md)
- [Database plan](docs/DATABASE_PLAN.md)
- [API plan](docs/API_PLAN.md)
- [Security plan](docs/SECURITY_PLAN.md)
- [Deployment plan](docs/DEPLOYMENT_PLAN.md)

## Proposed top-level structure

```text
Jeevasetu_wellness/
├── frontend/                 # Next.js application only
├── backend/                  # Django/DRF modular monolith
├── infrastructure/           # Docker, proxy, and deployment configuration
├── docs/                     # Architecture and operating documentation
├── scripts/                  # Cross-platform developer/CI helpers
├── .github/workflows/        # CI/CD workflows
├── .env.example              # Non-secret configuration contract
├── docker-compose.yml        # Local service orchestration
└── README.md
```

## Local setup

Prerequisites are Python 3.12+, Node.js 24+, pnpm 11.9.0, and optionally Docker Desktop with Compose.

1. Copy `.env.example` to `.env` and keep the local file out of Git.
2. Create a virtual environment under `backend/.venv` and install `backend/requirements/development.txt`.
3. Run `pnpm install --frozen-lockfile` from `frontend/`.
4. Start individual development servers or run `docker compose up --build`. Compose also starts the infrastructure-only Celery worker and Beat scheduler.

The frontend is served at `http://localhost:3000/`. Backend infrastructure routes are:

- Liveness: `http://localhost:8000/api/v1/health/live/`
- Aggregate readiness: `http://localhost:8000/api/v1/health/ready/`
- Component readiness: `/api/v1/health/ready/database/`, `/redis/`, and `/celery/`
- OpenAPI schema: `http://localhost:8000/api/v1/schema/`
- Swagger UI: `http://localhost:8000/api/v1/docs/`
- Redoc: `http://localhost:8000/api/v1/redoc/`

Development tenancy verification routes use the `X-Organization-Slug` request header:

- Active organization context: `GET /api/v1/tenancy/context/`
- Clinics available through active clinic mappings: `GET /api/v1/tenancy/clinics/`
- Tenant- and clinic-scoped lookup: `GET /api/v1/tenancy/clinics/{id}/`

These routes require an authenticated Django request identity and active membership. They are isolation probes, not public business APIs; no privileged-user bypass is enabled.

Identity API routes are under `/api/v1/auth/`:

- `POST register/`, `login/`, `refresh/`, and `logout/`
- `POST password/change/`, `password/reset/request/`, and `password/reset/confirm/`
- `GET`, `PUT`, or `PATCH profile/`

Access tokens expire after five minutes. Refresh tokens expire after one day, rotate on use, and blacklist the submitted token. Password-reset requests return a generic response and store only a single-use token digest; delivery-provider integration is intentionally absent.

## Quality commands

The root Makefile groups the common commands. Equivalent commands can be run directly from each application directory:

- Backend: Ruff format/lint, pytest, Django system check, and migration drift check.
- Frontend: ESLint, Vitest, TypeScript checking, and the Next.js production build.
- Containers: `docker compose config` validates the local service definition.

## Delivery principles

- Make small, reviewable changes and preserve a clean Git milestone at each phase.
- Keep business logic in domain services, not views, serializers, React components, or Celery tasks.
- Treat accessibility, security, observability, privacy, and automated tests as acceptance criteria.
- Do not store secrets, clinical documents, or production data in Git.
