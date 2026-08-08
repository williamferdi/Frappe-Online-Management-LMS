#!/bin/bash
# Wire the issued certificate into the site config and regenerate nginx with TLS.
set -euo pipefail

DOMAIN=online.sibbc.org
BENCH=/home/theiox/frappe-bench
LIVE=/etc/letsencrypt/live/$DOMAIN

cd "$BENCH"

run_as_bench() {
  sudo -u theiox env PATH="/home/theiox/.local/bin:/usr/local/bin:/usr/bin:/bin" \
    HOME=/home/theiox bash -c "cd $BENCH && $*"
}

echo "### pointing the site at the certificate"
run_as_bench "bench --site $DOMAIN set-config ssl_certificate $LIVE/fullchain.pem"
run_as_bench "bench --site $DOMAIN set-config ssl_certificate_key $LIVE/privkey.pem"

echo "### site_config ssl entries"
grep -E 'ssl_' "$BENCH/sites/$DOMAIN/site_config.json"

echo "### regenerating nginx config with TLS"
run_as_bench "bench setup nginx --yes"

echo "### listen directives now"
grep -nE 'listen|ssl_certificate |return 301' "$BENCH/config/nginx.conf" | head

nginx -t
systemctl restart nginx

echo "### listeners"
ss -tln | grep -E ':80 |:443 ' || true
echo "TLS_WIRED_OK"
