# Deployment Plan

## Environments

- Local: Docker Compose with Next.js, Django, Celery worker, optional scheduler, PostgreSQL, and Redis. Developer mail/storage emulators may be added.
- CI: ephemeral services and isolated test databases; no production secrets or data.
- Staging: production-like managed services, synthetic data, separate credentials/accounts, provider sandboxes.
- Production: isolated network and data stores, managed secrets, backups, monitoring, controlled deployment, and audited access.

Environment configuration follows a documented `.env.example` contract locally and a managed secret/config service remotely. Secrets and environment-specific credentials never enter images or Git.

## Container and traffic layout

```text
DNS/CDN/WAF
    |
Load balancer or Nginx edge
    |-- Next.js service
    |-- Django ASGI/WSGI service (/api, admin as restricted)
            |-- Managed PostgreSQL
            |-- Managed Redis
            |-- Private object storage
    |-- Celery worker pools
    +-- Celery scheduler (single active instance)
```

Static/media handling, Nginx, CDN, and exact application server are chosen in the production phase. PostgreSQL and Redis must not be publicly reachable. Keep web, worker, and scheduler images based on one tested backend artifact while running distinct commands.

The local topology now runs one Django web service, one Celery worker, and one single-instance Celery Beat scheduler from the same backend image. Liveness is used for process checks; aggregate readiness gates dependent frontend startup, while PostgreSQL, Redis, worker, and Beat have service-specific checks. Compose reads credentials from `.env` and refuses missing PostgreSQL values instead of embedding secret fallbacks. Production must use a managed secret store rather than an environment file.

## CI pipeline

For every pull request:

1. Validate formatting, linting, frontend types, backend checks, and migrations.
2. Run frontend unit/component tests and backend unit/integration tests using PostgreSQL and Redis-compatible services.
3. Validate OpenAPI and frontend contract compatibility.
4. Run secret, dependency, static-code, and container/IaC scans.
5. Build immutable frontend/backend images and verify production builds.
6. Publish test and coverage results; block merge on required checks.

Use GitHub Actions with least-privilege permissions, pinned action versions/commit SHAs, protected environments, and OIDC federation to cloud roles instead of long-lived cloud keys.

## Release pipeline

1. Merge reviewed code to the protected main branch and tag/version the immutable artifacts.
2. Deploy the same artifacts to staging; apply migration compatibility checks and smoke tests.
3. Run end-to-end, accessibility, security, and targeted performance tests.
4. Require production approval initially; deploy with rolling or blue/green strategy.
5. Run backwards-compatible migrations before switching traffic; perform destructive cleanup only in a later release.
6. Verify health, error rate, latency, queues, critical business flows, and migration state.
7. Roll back application traffic if thresholds fail; use forward-fix/restore procedures for data migrations.

## AWS-compatible target

- Containers: ECS/Fargate, EKS, or an equivalent managed container platform; choose the simplest team-operable option.
- Database: managed PostgreSQL with Multi-AZ capability, encryption, automated backups, point-in-time recovery, and connection pooling.
- Cache/queue: managed Redis-compatible service with private networking and workload-appropriate persistence policy.
- Storage: S3-compatible private buckets, encryption, versioning/lifecycle controls, malware scan workflow, and short-lived signed access.
- Edge: managed load balancer, TLS certificates, DNS, CDN/WAF as justified; Nginx only where it adds required routing/control.
- Secrets: Secrets Manager/Parameter Store equivalent; workload identity/roles, no static credentials.
- Observability: centralized structured logs, metrics, traces/error reporting, dashboards, alerts, and protected audit retention.
- Infrastructure: reviewed infrastructure as code with isolated state and environment boundaries.

## Scaling and resilience roadmap

- Scale stateless web services horizontally from request/CPU/latency metrics.
- Scale Celery worker pools separately by queue depth and task class; isolate slow integrations from time-critical notifications.
- Use database connection budgets/pooling, query thresholds, read replicas only after evidence, and controlled cache TTLs.
- Define and test RPO/RTO, backup restoration, regional/provider outage behavior, graceful degradation, and retry storms.
- Perform load tests before launch and major traffic events using production-like data shapes without personal data.

## Deployment phases

- Phase 1: local Compose, CI, health checks, configuration contract.
- Phases 2–5: staging environment, preview/test artifacts, migration discipline, provider sandboxes.
- Phase 6: production IaC, Nginx/edge decision, managed services, WAF, monitoring, alerting, backups, recovery and rollback drills.
- Post-launch: tune capacity from telemetry; add multi-region or service decomposition only when justified by measured needs and recovery objectives.

## Production readiness confirmations

Business owners must approve launch region, expected concurrent/peak traffic, availability SLO, RPO/RTO, maintenance windows, budget, data residency, retention, vendor choices, on-call ownership, incident contacts, and rollback authority.
