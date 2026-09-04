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
- `/app/matrix_token.json` points to `/data/matrix_token.json` so the verified
  Matrix session survives process and Machine restarts.

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

Matrix connection values:

- `MATRIX_HOMESERVER`
- `MATRIX_USER_ID`
- `MATRIX_ACCESS_TOKEN` for the Continuwuity production bot
- `MATRIX_DEVICE_ID` returned with the Continuwuity service token
- `MATRIX_PASSWORD` for a homeserver that supports password login
- `MATRIX_ROOM_ID`
- `PUBLIC_MATRIX_ROOM_IDS`

An access token requires its device ID. The bot first tries a verified saved
session. It then verifies `MATRIX_ACCESS_TOKEN`. It uses `MATRIX_PASSWORD` as a
fallback when one is configured.

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

## Create the Continuwuity bot account

Continuwuity 26.8.1 supports service access tokens for bots while delegated
OAuth is active. Run these commands as a server administrator in the Continuwuity
admin room.

Create a local bot account. Continuwuity returns a generated password when the
password argument is omitted:

```text
!admin users create ratichat-bot
```

Use that password once to issue the service token:

```text
!admin users issue-token ratichat-bot <generated-password>
```

The response contains an access token and a device ID. Record both in the team
password vault. Store the access token in Fly only as `MATRIX_ACCESS_TOKEN`.
Set the returned device ID as `MATRIX_DEVICE_ID`. Keep the generated account
password out of the bot runtime.

Invite `@ratichat-bot:rati.chat` to the approved room from an administrator's
Matrix client. An administrator can also force the local account into the room:

```text
!admin users force-join-room @ratichat-bot:rati.chat !approved-room:rati.chat
```

Set the canonical room ID in both `MATRIX_ROOM_ID` and
`PUBLIC_MATRIX_ROOM_IDS`. Start the bot. Confirm token verification, Matrix
sync, encrypted-room access, and one approved-room reply. Then disable new
login sessions for the bot account:

```text
!admin users disable-login @ratichat-bot:rati.chat
```

Continuwuity keeps the issued session active after login is disabled. Token
rotation starts with `!admin users enable-login`, then issues and verifies a new
token before login is disabled again. See the current
[Continuwuity user admin command reference](https://continuwuity.org/reference/admin/users).

## First live deployment

Reserve the final app name in Fly before running the workflow. The config uses
`ratichat-bot-prod` as the proposed name. Create the app in the chosen Fly
organization. Create an app-scoped deploy token. Add the runtime secrets in
Fly. Add `FLY_RATICHAT_BOT_DEPLOY_TOKEN` to the GitHub `production`
environment. Complete the Continuwuity bot account flow above and place its
access token and device ID in Fly before the first bot deploy.

Run **Deploy RatiChat bot to Fly** from the `main` branch. Enter the reserved
app name. The workflow validates the config, deploys with Fly high availability
disabled, fixes the `app` process group at one Machine, and prints final status.
The first deploy creates the 3 GB volume in `sjc`.

After the first deploy, confirm these items in Fly:

- The `app` process group has one running Machine in `sjc`.
- The Machine has 1 GB of memory.
- `ratichat_bot_data` is 3 GB and attached at `/data`.
- The TCP service check passes.
- The logs show configured-token verification and Matrix sync.
- `/app/matrix_token.json` resolves to the file on `/data`.
- The Farcaster signer value is absent from the running process.

Fly Volume snapshots have a five-day default retention period. Add an external
SQLite backup before this bot becomes the only copy of important history.
