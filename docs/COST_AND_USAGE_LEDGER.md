# Cost and usage ledger

Status: ready for the invited pilot

Owner: service operator

Update time: invoice close, once each month

## Budget rule

The pilot has these limits:

- fixed platform target: $25 per month or less
- model budget: $10 per month, with an alert at $8
- Neynar budget: free plan
- total cash cap: $35 per month, before the existing domain allocation and tax

Any paid Neynar plan, larger Fly machine, extra active machine, or managed
database goes through the upgrade check in
[DEPLOYMENT_OPTIONS.md](DEPLOYMENT_OPTIONS.md#upgrade-rules).

Keep Fly machine-creating autoscaling off during the pilot. Check the
month-to-date Fly bill each day. Record the check in the daily table below.
The model alert and stop are enforced inside RatiChat.

## Launch checkpoint: 2026-09-04

The four production app names are reserved on Fly.io.

| Fly app | Launch state | Machine | Live volume | Region |
| --- | --- | --- | --- | --- |
| `ratichat-chat` | Running | One `shared-cpu-1x`, 256 MB | - | `sjc` |
| `ratichat-id` | Reserved; no Machine yet | - | `pocket_data`, 1 GB | `sjc` |
| `ratichat-matrix` | Reserved; no Machine yet | - | `matrix_data`, 10 GB | `sjc` |
| `ratichat-bot-prod` | Reserved; no Machine yet | - | - | - |

Actual Fly invoice values are pending. The fixed values in the `Launch plan`
row remain planning estimates until they are replaced with invoice values.

## Daily month-to-date checks

Add one row after each daily Fly bill check. Keep provider usage counts
month-to-date so the last row can be reconciled with the monthly invoice.

| Check date | Fly MTD bill | Running Machines | Provisioned volume | Accepted Matrix events | Accepted Farcaster events | Completed replies | Model input / output tokens | Neynar credits | Evidence or note |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-09-04 | pending | 1 | 11 GB | pending | pending | pending | pending | pending | Launch infrastructure checkpoint |
| YYYY-MM-DD | $0.00 | 0 | 0 GB | 0 | 0 | 0 | 0 / 0 | 0 | Link to billing and usage evidence |

## Monthly cost ledger

Copy one row at the end of each billing month. Use invoice values in USD.

| Month | Fly compute | Volumes | Snapshots | Tigris | Egress | Neynar | Models | Domain allocation | Tax | Total | Active identities | Cost per active identity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Launch plan | $19.71 | $2.10 | $0.00 | $0.00 | up to $3.19 | $0.00 | up to $10.00 | record actual / 12 | record actual | capped at $35 plus domain and tax | - | - |

`Active identities` means Matrix accounts or Farcaster accounts that sent at
least one accepted human message during the month. A person active on both
platforms counts twice until they choose to link those accounts.

`Cost per active identity = total monthly cost / active identities`

## Service attribution

Record each invoice line under one owner. This keeps shared hosting costs and
usage-based provider costs visible.

| Cost owner | Included costs | Allocation rule |
| --- | --- | --- |
| Web chat | Element Web compute and certificates | Direct |
| Matrix service | Continuwuity compute, volume, snapshots, and Matrix backup share | Direct |
| Identity | Pocket ID compute, volume, and backup share | Direct |
| Bot platform | Bot compute, bot volume, and shared monitoring | Split by accepted Matrix and Farcaster bot jobs |
| Matrix bot use | Model cost for Matrix jobs | Direct from job metadata |
| Farcaster bot use | Neynar cost and model cost for Farcaster jobs | Direct from job metadata |
| Shared | Domain, shared backup storage, and shared traffic | Equal service split, with the rule recorded |

For shared bot compute:

`platform share = bot platform cost * platform accepted jobs / all accepted jobs`

Each durable bot job should record its platform, provider request count, model,
input tokens, output tokens, completion state, and calculated provider cost.
Store aggregate values in this ledger. Keep message text out of cost records.

Keep one hourly aggregate record with these fields:

- time, environment, service, Fly app, process group, Machine, and region
- CPU type, memory, started seconds, stopped seconds, and root file-system GB
- provisioned, used, snapshot, and backup storage GB
- public egress and private cross-region traffic GB
- registered users, active users, accepted events, and completed replies
- model tokens, Neynar credits, retries, provider cost, and result
- price version, estimated cost, and provider invoice line

## Monthly uptake ledger

| Month | Invites sent | New Matrix accounts | Matrix MAU | Farcaster engaged identities | Four-week returning identities | Human messages | Completed bot replies | Blocked by budget | Availability | Restore time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Launch plan | - | - | - | - | - | - | - | - | 99.5% target | 60 minute target |

Use these definitions every month:

- **Matrix MAU:** Matrix accounts that sent at least one human message in the
  month.
- **Farcaster engaged identities:** Farcaster accounts that mentioned or
  replied to RatiChat and passed intake checks.
- **Four-week returning identities:** active identities that were also active
  in the prior four-week period.
- **Human messages:** accepted inbound messages after replay and bot filtering.
- **Completed bot replies:** replies confirmed by Matrix or Farcaster.
- **Blocked by budget:** valid requests skipped because a provider cap was met.
- **Availability:** minutes ready divided by minutes in the month.
- **Restore time:** the last measured backup-to-ready drill time.

## Provider measures

Record these values beside the monthly invoice or in its linked evidence:

| Provider | Measures |
| --- | --- |
| Fly.io | machine-seconds by app, provisioned volume GB, snapshot GB, public egress GB |
| Tigris | average stored GB, Class A requests, Class B requests |
| Neynar | credits used, calls by endpoint, webhook events, rate-limit responses |
| Model provider | input tokens, output tokens, cached tokens, calls, cost by model and platform |
| Domain registrar | annual renewal divided by 12 |
| Backup runner | started seconds and storage requests when it uses a separate Machine |

Keep this deployment evidence with each monthly record:

- Element Web, Continuwuity, and Pocket ID image tags and digests
- configuration version and deployment commit
- successful and failed OIDC login counts
- passkey recovery drill result
- Matrix encryption recovery drill result
- last backup ID and restore drill result

## Month-end review

1. Copy exact invoice values into the cost ledger.
2. Reconcile provider totals with job-level counters.
3. Record active identities and returning identities.
4. Calculate total cost per active identity.
5. Calculate model cost per completed bot reply.
6. Explain any line that changed by more than 20%.
7. Check the upgrade rules.
8. Keep the current budget when the service meets its targets.
9. Review compute reservations after two stable months.

The month-end note should link to invoice evidence, monitoring evidence, and the
latest restore drill. Keep credentials and personal message data out of those
records.
