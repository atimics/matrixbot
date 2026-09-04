# RatiChat deployment options

Status: proposed for the invited pilot

Last reviewed: 2026-09-03

## Decision

Use the smallest Fly.io design for the invited pilot:

- Continuwuity for the Matrix homeserver
- RocksDB on a Fly Volume for Matrix state and media
- Pocket ID with SQLite on a Fly Volume for passkey login
- Element Web for the browser chat client
- RatiChat as one active bot process for Matrix and Farcaster
- Tigris for encrypted backup copies
- Neynar's free developer plan for Farcaster

This design keeps the fixed platform estimate at **$21.81 per month** in Fly's
San Jose region. The pilot operating cap is **$35 per month**, including up to
$10 of model use and a small allowance for traffic. The existing domain is
tracked as a monthly allocation.

The estimate is a planning value. The [cost and usage
ledger](COST_AND_USAGE_LEDGER.md) records invoice values after launch.

## Pilot service map

| Host | Service | Pilot size | State |
| --- | --- | --- | --- |
| `chat.rati.chat` | Element Web | 1 shared CPU, 256 MB | Stateless |
| `matrix.rati.chat` | Continuwuity | 1 shared CPU, 1 GB | 10 GB volume |
| `id.rati.chat` | Pocket ID | 1 shared CPU, 512 MB | 1 GB volume |
| `bot.rati.chat` | RatiChat API and worker | 1 shared CPU, 1 GB | 3 GB volume |
| `rati.chat` | Matrix discovery | Served by the web app | Stateless |

All services start in one Fly region. This keeps private traffic local. The
Matrix identity domain is `rati.chat`, so users receive IDs such as
`@alice:rati.chat`.

Element Web uses native Matrix OAuth against Continuwuity. Continuwuity
delegates user authentication to Pocket ID over OIDC. Pocket ID verifies the
passkey. This delegated flow puts Continuwuity in OAuth-only mode. Test the
exact Element Web image and each supported desktop or mobile client before
launch. Issue RatiChat an admin-managed legacy access token and test its full
restart flow.

The first release uses invited accounts. Each person enrolls two independent
passkeys on separate authenticators. A second passkey restores login access.
Matrix encryption recovery is a separate user flow.

## Fixed cost estimate

The estimate uses Fly's published San Jose examples and storage prices on
2026-09-03. It budgets for every Machine to stay on all month. Element Web may
cost less when it stops during idle periods.

| Item | Quantity | Monthly estimate |
| --- | ---: | ---: |
| Element Web machine, 256 MB | 1 | $2.32 |
| Continuwuity machine, 1 GB | 1 | $6.79 |
| Pocket ID machine, 512 MB | 1 | $3.81 |
| RatiChat machine, 1 GB | 1 | $6.79 |
| Matrix volume, 10 GB | 1 | $1.50 |
| Pocket ID volume, 1 GB | 1 | $0.15 |
| RatiChat volume, 3 GB | 1 | $0.45 |
| Fly volume snapshots | Under 10 GB of stored snapshots | $0.00 expected |
| Tigris backup storage | Under 5 GB | $0.00 expected |
| Backup job | Runs inside the Matrix app | $0.00 extra |
| Neynar developer plan | Under 10 million credits | $0.00 expected |
| **Fixed platform total** |  | **$21.81** |

Traffic, model calls, domain renewal, and any tax are recorded from the actual
bill. Public egress in North America is $0.02 per GB. Model use has an initial
$10 monthly cap. Send an alert at $8. Pause new model work at $10 while
ordinary Matrix chat stays available.

The baseline uses shared IPv4 addresses and the included certificate allowance.
Keep a fixed Machine count. Leave machine-creating autoscaling off. Check the
Fly month-to-date bill each day because Fly does not currently provide billing
alerts.

## Available options

| Option | Authentication | Expected base cost | Availability shape | Recovery model |
| --- | --- | ---: | --- | --- |
| Continuwuity and RocksDB | Native Matrix OAuth delegated to Pocket ID | $22-$25 per month | One active stateful server | Fly snapshot or tested operator-led Tigris restore |
| Synapse and self-run PostgreSQL | Synapse OIDC to Pocket ID through Matrix SSO | $35-$50 per month | Single database node | Operator-managed database backup and restore |
| Synapse, MAS, and Fly Managed Postgres | Native Matrix OAuth through MAS and Pocket ID | $65-$80 per month | Managed database failover | Managed database backup and recovery |

### Option 1: Continuwuity and RocksDB

Continuwuity keeps its database and media under one data directory. It supports
online RocksDB backups and delegated OIDC. This removes PostgreSQL and Matrix
Authentication Service from the pilot.

The Matrix volume belongs to one Fly host. Daily Fly snapshots and hourly
encrypted backups copied to a private Tigris bucket provide recovery. The
hourly job creates a complete RocksDB backup generation, copies media, and adds
the signing key, configuration, and version manifest. It encrypts the archive
before upload. Run this job inside the Matrix app. Add its compute to the ledger
if it later becomes a separate service.

Restoring an online RocksDB backup is an operator-led file reconstruction. Keep
a stopped replacement Machine definition ready. These become measured targets
after the first drill:

- recovery point: one hour
- recovery time: one hour after the operator starts recovery
- monthly service availability: 99.5%

Run a restore drill before inviting users and once each month.

### Option 2: Synapse and self-run PostgreSQL

Synapse uses PostgreSQL for a production service. This estimate uses Synapse's
direct OIDC connection to Pocket ID and its Matrix SSO flow. A small self-run
database lowers the cash cost. The pilot shape has one database node. The
operator owns database updates, backups, and recovery drills. Add database
replication as a separately costed reliability step.

Choose this option when a required Matrix client or feature works best with the
Synapse stack. Add Matrix Authentication Service when native Matrix OAuth is a
requirement. MAS adds another service and also uses PostgreSQL.

### Option 3: Synapse and Fly Managed Postgres

This estimate uses Synapse, Matrix Authentication Service, Pocket ID, and Fly
Managed Postgres. Fly Managed Postgres starts at $38 per month plus $0.28 for
each provisioned GB. It includes high availability, backups, recovery,
connection pooling, and automatic failover. This option earns its added cost
when measured demand or a service agreement needs those features.

## Identity decision

Run the internal acceptance test with a disposable database and test domain.
Initialize the production database once with `server_name = "rati.chat"` before
the first production account. Continuwuity treats the server name as part of
the database identity and requires a database wipe to change it.

Continuwuity lists migration from Synapse as unsupported. A future move to
Synapse would need a custom migration that preserves users, rooms, events,
media, devices, encryption state, and the server signing identity. Launching
`rati.chat` therefore includes an explicit decision to use Continuwuity as its
long-term homeserver.

Keep `https://id.rati.chat` as the stable Pocket ID origin. Set Pocket ID's
`APP_URL` to this HTTPS address. Back up its SQLite database and
`ENCRYPTION_KEY`. Store the Pocket ID key and OIDC client secret in Fly secrets
and in a separate encrypted recovery record.

Before the first external account is created, verify:

1. Pocket ID can enroll two passkeys on separate authenticators.
2. Either passkey can sign in through Pocket ID.
3. The pinned Element Web image completes native OAuth through Continuwuity.
4. Each supported desktop and mobile client completes sign-in.
5. A fresh browser restores encrypted Matrix keys and history through the
   chosen Matrix recovery method.
6. RatiChat restores its admin-issued token, joins an approved room, and
   replies.
7. A Matrix backup restores into a fresh Machine.
8. The restored server keeps the same users, rooms, signing key, and media.
9. The team accepts Continuwuity as the long-term homeserver for `rati.chat`.

## Launch gates

The low-cost service goes live when these checks pass:

- [PR #43](https://github.com/atimics/ratichat/pull/43) is merged so an idle
  clock tick does not create model spend and Neynar uses its current API header.
- Continuwuity 26.8.1 or a newer tested security patch is pinned by image
  digest. Element Web and Pocket ID images are also pinned by digest.
- Native OAuth, legacy bot-token, account-linking, and supported-client tests
  pass against the pinned images.
- Accepted Matrix and Farcaster events enter a durable inbox.
- Replies use a durable outbox and stable idempotency keys.
- The current Neynar webhook signature and payload contract have tests.
- Public chat users have a small, enforced tool set.
- Matrix tokens, device state, sync position, and bot data live under `/data`.
- Live and ready checks cover Matrix sync, the worker, storage, and Farcaster
  intake.
- The model budget has alerts and a hard monthly stop.
- Backup and restore drills meet the pilot recovery targets.
- Cost and uptake measures are visible without storing message text.
- Aggregate OIDC login and account-recovery results are visible without user
  identifiers.

## Upgrade rules

Review a higher-cost option when one of these signals lasts long enough to be
measured:

- service availability stays below 99.5% for a month
- a restore drill takes more than one hour
- CPU or memory stays above 75% for three days
- a volume stays above 70% full for seven days
- Neynar uses 70% of its free credits in a month
- the model cap blocks at least 10% of valid bot requests
- a required client needs Synapse or Matrix Authentication Service
- operator recovery and database work takes more than two hours in a month
- the service approaches 100 persistent accounts or a paid community launch

Every funding request includes two full monthly ledger rows, active-user and
retention numbers, the current cost per active user, the exact limit, the new
monthly cap, and the result expected from that increase.

After two stable billing months, review annual shared-compute reservations.
They can lower the steady compute cost. Buy them only when the final Machine
sizes have stayed stable through both months.

## Sources

- [Fly.io resource pricing](https://fly.io/docs/about/pricing/)
- [Fly.io San Jose cost examples](https://fly.io/docs/about/cost-management/)
- [Fly.io volume design](https://fly.io/docs/volumes/overview/)
- [Fly Managed Postgres](https://fly.io/docs/mpg/)
- [Tigris pricing](https://www.tigrisdata.com/pricing/)
- [Continuwuity configuration](https://continuwuity.org/reference/config)
- [Continuwuity backup guide](https://continuwuity.org/maintenance)
- [Continuwuity release history](https://github.com/continuwuity/continuwuity/blob/main/CHANGELOG.md)
- [Continuwuity project and migration notes](https://github.com/continuwuity/continuwuity)
- [Pocket ID user management](https://pocket-id.org/docs/setup/user-management)
- [Pocket ID database and key configuration](https://pocket-id.org/docs/configuration/environment-variables)
- [Neynar developer pricing](https://neynar.com/developer)
- [Synapse database guidance](https://element-hq.github.io/synapse/latest/setup/installation.html#using-postgresql)
- [Matrix Authentication Service database configuration](https://element-hq.github.io/matrix-authentication-service/reference/configuration.html#database)
