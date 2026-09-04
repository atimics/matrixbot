# Self-service RatiChat signup

The intended flow is: open chat, choose **Sign up**, enter account details,
add a passkey, and continue into Matrix. Pocket ID assigns chat access during
signup through one default member group.

## Configure signup once

Use the existing ordinary chat group, currently named **ratichat** in
production. On a fresh installation, create a group named **RatiChat members**.

1. In **OIDC Clients → RatiChat Matrix → Allowed User Groups**, select that
   group and save. Keep the client restricted to the chat group.
2. Open **Application Configuration → User Creation**.
3. Under **User Groups**, select the same group. Pocket ID applies it to each
   new account automatically.
4. Set **Enable User Signups** to **Open** for public registration, or
   **Signup with token** for registration through an invite link. Save the
   signup mode and default group together when the operator approves launch.
5. Under **General**, set **Application Name** to **RATi Chat**,
   **Accent Color** to **Amber**, and **Home Page** to **RATi Chat**. Save.

The home-page choice is included in this image. It points to
`https://chat.rati.chat/#/login` and handles direct signup visits. A signup
started from chat returns to its original login session.

An invite link can also assign the chat group. Select this group when creating
the signup token. Both signup modes use the same automatic membership rule.
Existing accounts keep their current groups; add the operator's account to the
chat group for the first acceptance check.

Pocket ID's **UI configuration** mode stores these settings in its database.
Use the admin form for this deployment. The `ALLOW_USER_SIGNUPS`,
`SIGNUP_DEFAULT_USER_GROUP_IDS`, `APP_NAME`, `ACCENT_COLOR`, and `HOME_PAGE_URL`
environment variables apply when `UI_CONFIG_DISABLED=true` is selected for a
separate deployment managed through environment variables.

## Why this image has a patch

Pocket ID 2.14.0 supports open signup and default groups. Its frontend sends a
new user to account settings after passkey setup. Its OIDC interaction screen
also needs a signup entry point.

`patches/signup-return.patch` adds that entry point and carries the return
path through signup and passkey setup. A completed passkey setup returns to
the OIDC flow or the configured home page. Choosing **Skip for now** continues
to account settings, where the person can finish passkey setup.

Return paths are limited to local `/authorize` and `/interaction` routes.
The OIDC server keeps control of the final client callback and consent flow.

The build uses Pocket ID commit
`5521266227205dccb57ba58d820c833a5701346d` (v2.14.0). The source archive,
Node image, Go image, and final Pocket ID image each have a checksum. The
patch applies to that exact source. The app version is
`2.14.0-ratichat.1`.

## Check and deploy

From the repository root:

```sh
./scripts/validate-matrix-pilot.sh
docker build --tag ratichat-pocket-signup deploy/matrix/pocket-id
```

The image build runs the signup navigation tests, frontend build, frontend
type checks, and Go build. The Matrix infrastructure workflow also starts the
image and checks `/healthz`.

After the PR is merged and the operator approves the signup policy, deploy
the existing Pocket ID app:

```sh
fly deploy deploy/matrix/pocket-id \
  --config deploy/matrix/pocket-id/fly.toml
```

Keep the existing Pocket ID volume, encryption key, OIDC client, and public
origin. Save the settings above after the image is healthy.

## Acceptance check

Use a fresh browser session and a test account approved by the operator:

1. Start from `https://chat.rati.chat` and choose **Sign up** on the identity
   screen.
2. Complete account details and add a passkey.
3. Confirm that the browser resumes the original Matrix login.
4. Complete the Matrix account setup and enter chat.
5. Confirm that Pocket ID assigned the ordinary chat group automatically.
6. Sign out and sign in with that passkey.
7. Repeat the direct signup path from `https://id.rati.chat/signup`. After
   passkey setup, it should open chat through the configured home page.

The test account receives ordinary chat access. An administrator completes the
one-time group setup; each signup then follows the same self-service path.

## References

- [Pocket ID signup and invite links](https://pocket-id.org/docs/setup/user-management)
- [Pocket ID allowed groups](https://pocket-id.org/docs/configuration/allowed-groups)
- [Pinned signup page](https://github.com/pocket-id/pocket-id/blob/5521266227205dccb57ba58d820c833a5701346d/frontend/src/routes/signup/%2Bpage.svelte)
- [Pinned default group implementation](https://github.com/pocket-id/pocket-id/blob/5521266227205dccb57ba58d820c833a5701346d/backend/internal/service/user_service.go)
