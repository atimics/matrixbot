# syntax=docker/dockerfile:1.7

FROM node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS frontend-builder
RUN apk add --no-cache git && corepack enable
WORKDIR /build
ADD --checksum=sha256:788c6b85aaa5f67b70d39169afb76ecb5237a01218978284866cfce69003cce6 https://codeload.github.com/pocket-id/pocket-id/tar.gz/5521266227205dccb57ba58d820c833a5701346d /tmp/pocket-id.tar.gz
RUN tar -xzf /tmp/pocket-id.tar.gz --strip-components=1 -C /build
COPY patches/signup-return.patch /tmp/signup-return.patch
RUN git apply --check /tmp/signup-return.patch && git apply /tmp/signup-return.patch
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm --filter pocket-id-frontend install --frozen-lockfile
COPY tests/signup-navigation.test.mjs /build/frontend/src/lib/utils/signup-navigation.test.mjs
RUN node --test frontend/src/lib/utils/signup-navigation.test.mjs \
    && pnpm --filter pocket-id-frontend build \
    && pnpm --filter pocket-id-frontend check

FROM golang:1.26.6-alpine@sha256:3889b425f035be855a72fb4755265311293b6d414521f0a519d819df32222d83 AS backend-builder
WORKDIR /build/backend
COPY --from=frontend-builder /build/backend /build/backend
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath \
    -ldflags="-X github.com/pocket-id/pocket-id/backend/internal/common.Version=2.14.0-ratichat.1 -buildid=2.14.0-ratichat.1" \
    -o /build/pocket-id ./cmd

FROM ghcr.io/pocket-id/pocket-id:v2.14.0@sha256:01540977dcf4c7b41b1159f34d68e4632f2658d62790e460ca65a42722b13c4a
COPY --from=backend-builder /build/pocket-id /app/pocket-id
