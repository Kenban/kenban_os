#!/bin/bash -e

on_chroot << EOF
  
  mkdir -p "/home/${FIRST_USER_NAME}/data/default_images"
  mkdir -p "/home/${FIRST_USER_NAME}/data/default_templates"
  mkdir -p "/home/${FIRST_USER_NAME}/data/user_templates"
  mkdir -p "/home/${FIRST_USER_NAME}/kenban"

  git clone https://github.com/Kenban/kenban_os.git "/home/${FIRST_USER_NAME}/kenban"

  cp -r "/home/${FIRST_USER_NAME}/kenban/images/*" "/home/${FIRST_USER_NAME}/data/default_images"
  cp -r "/home/${FIRST_USER_NAME}/kenban/templates/*" "/home/${FIRST_USER_NAME}/data/default_templates"
  cp "/home/${FIRST_USER_NAME}/kenban/templates/macros.html" "/home/${FIRST_USER_NAME}/data/user_templates/"

  install -m 664 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/.profile" "/home/${FIRST_USER_NAME}/.profile"
  install -m 664 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/.xinitrc" "/home/${FIRST_USER_NAME}/.xinitrc"
  install -m 644 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/websocket-sync.service" "/etc/systemd/system/websocket-sync.service"
  install -m 644 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/websocket-local.service" "/etc/systemd/system/websocket-local.service"
  install -m 644 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/kenban-wifi-manager.service" "/etc/systemd/system/kenban-wifi-manager.service"
  install -m 644 "/home/${FIRST_USER_NAME}/kenban/pi-gen-files/kenbanxorg.conf" "/etc/X11/xorg.conf.d/kenban.conf"

  raspi-config nonint do_boot_behaviour B2
  sed -i 's/sam/${FIRST_USER_NAME}/g' /etc/systemd/system/getty@tty1.service.d/autologin.conf
  systemctl enable websocket-sync.service local-websocket.service kenban-wifi-manager.service

  mkdir -p /home/${FIRST_USER_NAME}/kenban/local-websocket/nodejs
  wget https://nodejs.org/dist/v18.13.0/node-v18.13.0-linux-x64.tar.xz
  tar -xvf node-v18.13.0-linux-x64.tar.xz -C /home/${FIRST_USER_NAME}/kenban/local-websocket/nodejs --strip-components=1

  pip install -r /home/${FIRST_USER_NAME}/kenban/requirements.txt
  cd /home/${FIRST_USER_NAME}/kenban/local-websocket && npm install

  chmod 755 /home/${FIRST_USER_NAME}/kenban/network/wifi-connect
  chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /home/${FIRST_USER_NAME}/kenban
  chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /home/${FIRST_USER_NAME}/data

  echo "$(( RANDOM % 60)) $(( RANDOM % 8)) $(( RANDOM % 30 + 1)) * * root ansible-pull -U https://github.com/kenban/kenban_os/ -C production" > /etc/cron.d/kenban-ansible-pull

EOF
