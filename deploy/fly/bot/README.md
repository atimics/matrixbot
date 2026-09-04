# RatiChat bot on Fly.io

This folder defines the first production Fly deployment for the RatiChat bot.
It is a low-cost single-instance design for the `sjc` region.

## Runtime shape

- One `shared-cpu-1x` Machine with 1 GB of memory.
- One 3 GB Fly Volume named `ratichat_bot_data`, mounted at `/data`.
- The Machine stays active. Fly Proxy auto-stop is off.
- Fly restarts the Machine after a failed process exit, with up to 10 retries.
- Fly sends `SIGTERM` and gives the process 30 seconds to close.
- A TCP check confirms that the API process accepts connections on port 8000.
- The SQLite database, Telegram cursor and queue, and Matrix device store use
  the volume.

The public `/health` route reports API reachability. The TCP check uses the
same narrow readiness claim. Matrix and Farcaster dependency checks can be
added when the runtime exposes them.

## Farcaster mode

This foundation runs Farcaster in observer-only mode. The Fly config records
`FARCASTER_OUTBOUND_ENABLED=false`. The startup wrapper clears
`FARCASTER_BOT_SIGNER_UUID` before Python starts. A Neynar API key can still be
used for inbound observation.

Enable outbound actions in a later reviewed rollout. That rollout should add a
working runtime gate, add the signer secret, and test one controlled cast.

## Secret names

Store values with `fly secrets set` so the repository contains names alone.

Core bot secrets:

- `ADMIN_API_TOKEN`
- `INTEGRATION_CREDENTIAL_KEY`
- `OPENROUTER_API_KEY`

Matrix connection secrets:

- `MATRIX_HOMESERVER`
- `MATRIX_USER_ID`
- `MATRIX_PASSWORD`
- `MATRIX_ROOM_ID`
- `PUBLIC_MATRIX_ROOM_IDS`
- `MATRIX_DEVICE_ID` when an existing device is reused

Farcaster observer secrets:

- `NEYNAR_API_KEY`
- `FARCASTER_BOT_FID`
- `FARCASTER_BOT_USERNAME`
- `FARCASTER_WEBHOOK_SECRET` when webhooks are enabled

Telegram secrets are optional:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_CHAT_IDS`
- `TELEGRAM_ALLOWED_SENDER_IDS`

The GitHub production environment needs one Actions secret:

- `FLY_RATICHAT_BOT_DEPLOY_TOKEN`: an app-scoped Fly deploy token with a short
  expiry. The workflow maps it to `FLY_API_TOKEN` for `flyctl`.

`FARCASTER_BOT_SIGNER_UUID` belongs to the later outbound rollout. The current
startup wrapper clears it.

## First live deployment

Reserve the final app name in Fly before running the workflow. The config uses
`ratichat-bot-prod` as the proposed name. Create the app in the chosen Fly
organization. Create an app-scoped deploy token. Add the runtime secrets in
Fly. Add `FLY_RATICHAT_BOT_DEPLOY_TOKEN` to the GitHub `production`
environment.

Run **Deploy RatiChat bot to Fly** from the `main` branch. Enter the reserved
app name. The workflow validates the config, deploys with Fly high availability
disabled, fixes the `app` process group at one Machine, and prints final status.
The first deploy creates the 3 GB volume in `sjc`.

After the first deploy, confirm these items in Fly:

- The `app` process group has one running Machine in `sjc`.
- The Machine has 1 GB of memory.
- `ratichat_bot_data` is 3 GB and attached at `/data`.
- The TCP service check passes.
- The logs show Matrix login and sync.
- The Farcaster signer value is absent from the running process.

Fly Volume snapshots have a five-day default retention period. Add an external
SQLite backup before this bot becomes the only copy of important history.
