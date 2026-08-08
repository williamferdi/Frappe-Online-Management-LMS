#!/bin/bash
# Enable name-based virtual hosting so bench emits an SSL server block.
#
# bench/config/nginx.py prepare_sites() only fills sites["that_use_ssl"] -- the
# list the template turns into `listen 443 ssl` -- when common_site_config has
# dns_multitenant set. Without it every site lands in "that_use_port" and gets a
# plain `listen 80`, no matter what ssl_certificate is in site_config.
set -euo pipefail

DOMAIN=online.sibbc.org
BENCH=/home/theiox/frappe-bench

run_as_bench() {
  sudo -u theiox env PATH="/home/theiox/.local/bin:/usr/local/bin:/usr/bin:/bin" \
    HOME=/home/theiox bash -c "cd $BENCH && $*"
}

echo "### enabling dns_multitenant"
run_as_bench "bench config dns_multitenant on"
grep -E 'dns_multitenant' "$BENCH/sites/common_site_config.json"

echo "### regenerating nginx config"
run_as_bench "bench setup nginx --yes"

echo "### listen / ssl directives"
grep -nE 'listen |ssl_certificate |server_name|return 301' "$BENCH/config/nginx.conf" | head -20

nginx -t
systemctl restart nginx

echo "### listeners"
ss -tln | grep -E ':80 |:443 ' || true
echo "DNS_MT_OK"
