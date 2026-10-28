#!/bin/sh
# Idempotent: proxy + reverse tunnel on Mac, /etc/hosts + proxy env on device (apk over USB net).
PROXY=$(cd "$(dirname "$0")/.." && pwd)/tools/venv/bin/proxy
# sshd on device has AllowTcpForwarding no, so no reverse tunnel: proxy listens on the USB iface IP.
MAC=172.16.42.2
pgrep -f "proxy --hostname $MAC --port 3128" >/dev/null || \
  nohup "$PROXY" --hostname $MAC --port 3128 --log-level ERROR >/tmp/proxy3128.log 2>&1 &
sleep 2
H=""
for h in mirror.postmarketos.org cdn.alpinelinux.org; do
  ip=$(dig +short A $h | grep -E '^[0-9.]+$' | head -1)
  [ -n "$ip" ] && H="$H$ip $h
"
done
[ -n "$H" ] || { echo "DNS lookup failed on Mac" >&2; exit 1; }
ssh palma "echo palma | sudo -S -p '' sh -c '
sed -i \"/# palma_net/d\" /etc/hosts
printf \"%s\" \"$(printf '%s' "$H" | sed 's/$/ # palma_net/')
\" >> /etc/hosts
printf \"export http_proxy=http://$MAC:3128\\nexport https_proxy=http://$MAC:3128\\n\" > /etc/profile.d/proxy.sh
printf \"Defaults env_keep += \\\"http_proxy https_proxy\\\"\\n\" > /etc/sudoers.d/proxy
chmod 440 /etc/sudoers.d/proxy'"
echo ok
