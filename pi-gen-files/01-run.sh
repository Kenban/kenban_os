#!/bin/bash -e

on_chroot << EOF

  mkdir -p "/home/${FIRST_USER_NAME}/data/default_images"
  mkdir -p "/home/${FIRST_USER_NAME}/data/default_templates"
  mkdir -p "/home/${FIRST_USER_NAME}/data/user_templates"

  git clone https://github.com/Kenban/kenban_os.git "/home/${FIRST_USER_NAME}/kenban"
  git -C "/home/${FIRST_USER_NAME}/kenban" checkout production
  mkdir -p "/home/${FIRST_USER_NAME}/kenban/logs"

  cp -R /home/${FIRST_USER_NAME}/kenban/images/* /home/${FIRST_USER_NAME}/data/default_images
  cp -R /home/${FIRST_USER_NAME}/kenban/templates/* /home/${FIRST_USER_NAME}/data/default_templates
  cp /home/${FIRST_USER_NAME}/kenban/templates/macros.html /home/${FIRST_USER_NAME}/data/user_templates/

  install -m 664 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/.profile" "/home/${FIRST_USER_NAME}/.profile"
  install -m 664 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/.xinitrc" "/home/${FIRST_USER_NAME}/.xinitrc"
  install -m 644 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/websocket-sync.service" "/etc/systemd/system/websocket-sync.service"
  install -m 644 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/websocket-local.service" "/etc/systemd/system/websocket-local.service"
  install -m 644 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/kenban-wifi-manager.service" "/etc/systemd/system/kenban-wifi-manager.service"
  install -m 644 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/kenbanxorg.conf" "/etc/X11/xorg.conf.d/kenban.conf"

  raspi-config nonint do_boot_behaviour B2
  sed -i 's/sam/${FIRST_USER_NAME}/g' /etc/systemd/system/getty@tty1.service.d/autologin.conf
  systemctl enable websocket-sync.service websocket-local.service kenban-wifi-manager.service

  mkdir -p /home/${FIRST_USER_NAME}/kenban/local-websocket/nodejs
  wget https://nodejs.org/dist/v18.15.0/node-v18.15.0-linux-arm64.tar.xz
  tar -xvf node-v18.15.0-linux-arm64.tar.xz -C /home/${FIRST_USER_NAME}/kenban/local-websocket/nodejs --strip-components=1

  python3 -m venv --system-site-packages /home/${FIRST_USER_NAME}/kenban/venv
  source /home/${FIRST_USER_NAME}/kenban/venv/bin/activate
  pip install -r /home/${FIRST_USER_NAME}/kenban/requirements.txt
  cd /home/${FIRST_USER_NAME}/kenban/local-websocket && npm install

  chmod 755 /home/${FIRST_USER_NAME}/kenban/network/wifi-connect
  chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /home/${FIRST_USER_NAME}/kenban
  chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /home/${FIRST_USER_NAME}/data

  chmod 755 /home/${FIRST_USER_NAME}/kenban/update.sh
  echo "0 2 1 * * ${FIRST_USER_NAME} bash /home/${FIRST_USER_NAME}/kenban/update.sh" > /etc/cron.d/kenban-update
  echo alias update="bash /home/${FIRST_USER_NAME}/kenban/update.sh --no-wait" >> /home/${FIRST_USER_NAME}/.bashrc
  chmod 600 /etc/cron.d/kenban-update

EOF
