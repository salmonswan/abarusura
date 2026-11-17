#!/bin/sh
# Writes directus/.env. On CI: throwaway random values. Locally: values from pass.
set -eu
cd "$(dirname "$0")"
[ -f .env ] && exit 0
umask 077
if [ -n "${CI:-}" ]; then
  db=$(openssl rand -hex 24)
  secret=$(openssl rand -hex 24)
  email=ci@example.org
  admin=$(openssl rand -hex 24)
else
  db=$(pass show abarusura/dev/db-password)
  secret=$(pass show abarusura/dev/directus-secret)
  email=$(pass show abarusura/dev/admin-email)
  admin=$(pass show abarusura/dev/admin-password)
fi
printf 'DB_PASSWORD=%s\nDIRECTUS_SECRET=%s\nADMIN_EMAIL=%s\nADMIN_PASSWORD=%s\n' \
  "$db" "$secret" "$email" "$admin" > .env.tmp
mv .env.tmp .env
