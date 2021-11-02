#!/bin/bash

# Fixes permission on /dev/vchiq
chgrp -f video /dev/vchiq
chmod -f g+rwX /dev/vchiq

# Set permission for sha file
chown -f viewer /dev/snd/*
chown -f viewer /data/.kenban/latest_kenban_sha

# Fixes caching in QTWebEngine
mkdir -p /data/.local/share/KenbanWebview/QtWebEngine \
    /data/.cache/KenbanWebview \
    /data/.pki
chown -Rf viewer /data/.local/share/KenbanWebview
chown -Rf viewer /data/.cache/KenbanWebview/
chown -Rf viewer /data/.pki

# Temporary workaround for watchdog
touch /tmp/kenban.watchdog
chown viewer /tmp/kenban.watchdog

# For whatever reason Raspbian messes up the sudo permissions
chown -f root:root /usr/bin/sudo
chown -Rf root:root /etc/sudoers.d
chown -Rf root:root /etc/sudo.conf
chown -Rf root:root /usr/lib/sudo
chown -f root:root /etc/sudoers
chmod -f 4755 /usr/bin/sudo

# SUGUSR1 from the viewer is also sent to the container
# Prevent it so that the container does not fail
trap '' 16

sudo -E -u viewer dbus-run-session python3 viewer.py &

# Waiting for the viewer
while true; do
  PID=$(pidof python3)
  if [ "$?" == '0' ]; then
    break
  fi
  sleep 0.5
done

# Exit when the viewer falls
while kill -0 "$PID"; do
  sleep 1
done
