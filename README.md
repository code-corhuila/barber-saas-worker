# barber-saas-worker

> Asynchronous jobs and background processing

Part of the **Barber Saas** distributed system — team `barber-saas`, Grupo 2.
Governance and documentation live in [`barber-saas-docs`](https://github.com/code-corhuila/barber-saas-docs).

## Branching

Three permanent branches. **None of them accepts a direct commit** — you enter through a child
branch and leave through a Pull Request.

```
develop  <--PR--  feat/... fix/... chore/...
qa       <--PR--  qa/...
main     <--PR--  release/...  hotfix/...
```

Promotion happens **by re-application** (`git cherry-pick -x`), never by merging one permanent
branch into another: `merge develop -> qa` and `merge qa -> main` do not exist in this model.

`main` requires **1 approval from `ariel5253`**. On `develop` and `qa` the team sets its own review
rule.

Full policy: `00-governance/branching-policy.md` in `barber-saas-docs`.

---

## BarberSaaS — what this repository is

`barber-saas-worker` (Python 3.12, standard library only, ADR-012) runs the platform's background
work. It exposes no business HTTP interface: only `GET /health` (norm 5.7.1).

- **Outbox relay (ADR-016):** every 5 s, for each producer (`PRODUCERS`), it reads up to 50 pending
  events (`GET /internal/v1/outbox-events`), delivers each to the consumers of its type
  (`POST /internal/v1/events` of loyalty-api and notifications-api; routing in
  `domain/model/routing.py`, the table of `02-domain/domain-events.md`) and confirms it
  (`.../published`, or `.../failed` with the reason).
- **Daily jobs:** `reminders-due` (18:00), `no-shows` (01:00) on appointment-api and `trials/expire`
  (02:00, FR-026) on platform-admin-api, Colombia time. The rules live in those services.

### Delivery rules (norm 5.7)

| Rule | How |
|---|---|
| One job per event type (5.7.a) | `DeliverEvent` per type inside each producer's `RelayOutbox` |
| Bounded retries with backoff and jitter (5.7.2) | network, 429 and 5xx: up to 8 attempts across runs, 5 s doubling to 5 min, +0–50 % jitter; a 4xx fails at once |
| Idempotency | at least once: consumers keep the envelope id; a consumer already served gets the event again and answers `DUPLICATE` |
| Correlation (5.7.3) | each run has its own `X-Correlation-Id`, sent on every call and in the run's log line |
| Bounded runs | 50 events per producer and 30 s per run; the rest waits for the next run |
| Own credential | `SERVICE_TOKEN` = `WORKER_SERVICE_TOKEN` (`sub: barber-saas-worker`), never versioned |

A consumer without a URL (not deployed yet) is not called: its events wait in the outbox. Attempts
are counted in memory: a restart gives an event its 8 attempts again.

```
src/worker/domain/            event, routing table, retry policy (imports nothing)
src/worker/application/       port/inbound/job.py, port/outbound/services.py, usecase/ (relay, daily job)
src/worker/adapter/           inbound: scheduler, health; outbound/http: urllib clients
apps/worker/__main__.py       composition root (environment → jobs)
```

### How to start it

As part of the platform: `./scripts/up.sh dev` in `barber-saas-infra-postgres`. Alone:
`PYTHONPATH=src:. SERVICE_TOKEN=... APPOINTMENT_API_URL=... python -m apps.worker` (`.env.example`).

### How it is tested

`pip install -e ".[dev]" && pytest && lint-imports`: the relay and daily jobs against fakes, the HTTP
adapters against a local server, and the import-linter contracts (domain alone, application without
network, adapters outside).
