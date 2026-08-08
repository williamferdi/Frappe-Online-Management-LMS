#!/bin/bash
# SIBBCS ERP - TLS for online.sibbc.org via Let's Encrypt.
#
# Standalone challenge, not webroot: Frappe's nginx template has no
# /.well-known/acme-challenge location and proxies everything unmatched to the
# backend, so a webroot challenge would 404. Standalone needs port 80 free, so
# nginx stops for a few seconds. The same stop/start is registered as renewal
# hooks so certbot's packaged timer can renew unattended.
#
# The cert paths are written into site_config.json rather than into the nginx
# file directly, because bench's nginx template reads ssl_certificate /
# ssl_certificate_key from there -- so `bench setup nginx` regenerates a correct
# TLS config instead of clobbering hand edits.
set -euo pipefail

DOMAIN=online.sibbc.org
EMAIL=william@sibbc.org
BENCH=/home/theiox/frappe-bench
LIVE=/etc/letsencrypt/live/$DOMAIN

export DEBIAN_FRONTEND=noninteractive
echo "### installing certbot"
apt-get install -y -qq --no-install-recommends certbot

echo "### requesting certificate (standalone)"
certbot certonly \
  --standalone \
  -d "$DOMAIN" \
  --email "$EMAIL" \
  --agree-tos --no-eff-email --non-interactive \
  --keep-until-expiring \
  --pre-hook  "systemctl stop nginx" \
  --post-hook "systemctl start nginx"

echo "### certificate files"
ls -l "$LIVE/fullchain.pem" "$LIVE/privkey.pem"

echo "### making the key readable by the nginx worker"
# certbot locks /etc/letsencrypt/{live,archive} to root; nginx reads the key as
# root in the master process, so default perms are fine. Just assert they exist.
test -s "$LIVE/fullchain.pem" && test -s "$LIVE/privkey.pem"

echo "### pointing the site at the certificate"
sudo -u theiox env PATH="/home/theiox/.local/bin:$PATH" \
  bench --site "$DOMAIN" set-config ssl_certificate "$LIVE/fullchain.pem" --parse >/dev/null 2>&1 \
  || sudo -u theiox env PATH="/home/theiox/.local/bin:$PATH" \
     bench --site "$DOMAIN" set-config ssl_certificate "$LIVE/fullchain.pem"
sudo -u theiox env PATH="/home/theiox/.local/bin:$PATH" \
  bench --site "$DOMAIN" set-config ssl_certificate_key "$LIVE/privkey.pem"

echo "### regenerating nginx config with TLS"
cd "$BENCH"
sudo -u theiox env PATH="/home/theiox/.local/bin:$PATH" bench setup nginx --yes

nginx -t
systemctl restart nginx

echo "### listeners"
ss -tln | grep -E ':80|:443' || true

echo "### renewal timer"
systemctl list-timers 'certbot*' --no-pager 2>/dev/null | head -3 || true
echo "TLS_OK"
