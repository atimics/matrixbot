# RATi manages its Matrix community

RATi uses one account for chat and a separate service account for server
commands. Both sessions run in the bot app. The model receives tool results;
credentials stay in the runtime.

## Available work

- Answer people in configured chat rooms and check live Matrix health.
- Change names and topics of configured public rooms.
- Publish or unpublish those rooms in the local directory.
- Read server uptime, memory use, and database backup results.
- Run an online database backup each day and after an operator request.

Management requests come from an operator's Matrix ID in a private control
room. The runtime checks the latest event's sender and room before execution.
Each change gets a durable SQLite receipt. Repeated processing of an event
reuses its receipt. Uncertain requests keep their status for operator review.

## Configure

The Fly configuration selects `BOT_CAPABILITY_PROFILE=matrix_steward`.
Set these values alongside the core bot secrets in README.md:

| Setting | Value |
| --- | --- |
| `MATRIX_USER_ID` | `@ratichat-bot:rati.chat` |
| `MATRIX_ACCESS_TOKEN`, `MATRIX_DEVICE_ID` | Chat account service session |
| `MATRIX_ROOM_ID` | Canonical public room ID |
| `PUBLIC_MATRIX_ROOM_IDS` | Public room ID and control room ID, comma separated |
| `MATRIX_MANAGED_ROOM_IDS` | Public room IDs owned by the chat account |
| `MATRIX_CONTROL_ROOM_ID` | Private operator room ID |
| `MATRIX_OPERATOR_USER_IDS` | Operator Matrix IDs, comma separated |
| `MATRIX_ADMIN_ACCESS_TOKEN` | Dedicated manager account service token |
| `MATRIX_ADMIN_ROOM_ID` | Continuwuity admin room ID |
| `MATRIX_ADMIN_SERVER_USER_ID` | `@conduit:rati.chat` |
| `MATRIX_BACKUP_INTERVAL_SECONDS` | `86400` for daily backups; `0` pauses the schedule |

Create `ratichat-bot` and `ratichat-manager` with Continuwuity's `users create`
and `users issue-token` commands. Give `ratichat-manager` server administration
with `users make-user-admin`. Keep `ratichat-bot` an ordinary server account;
make it the creator of the public room and control room. Give the human
operator room power level 100 in both rooms.

The manager account joins the server admin room. The chat account joins the
public room and control room. Approved room observation occurs before media
handling. The server admin room stays outside the AI conversation history.
The server command tool accepts four named operations and checks the sender
and reply event ID of each result.

When local room directory publication is restricted to server admins, publish
the initial public room through the server admin account. A room creator can
still manage its name and topic. The room publication tool reports the server's
permission result.

## Operator examples

In the control room, ask:

- "Check the Matrix server uptime."
- "Back up the server database."
- "Show the database backups."
- "Set our chat room topic to Welcome to RATi Chat."

Use the public room for conversation with RATi. Its topic should explain that
messages addressed to the bot are processed by its configured AI provider.

Verify an actual reply after launch, then test a room topic change and an
online backup from the operator room. Check that an ordinary user's public
message cannot run management tools. Volume snapshots and the online database
backup remain on Fly; keep an external copy for disaster recovery.
