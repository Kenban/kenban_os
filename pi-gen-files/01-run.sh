#!/bin/bash -e

mkdir -p "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/data/default_images"
mkdir -p "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/data/default_templates"
mkdir -p "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/kenban"

cp -r files/kenban_os/* "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/kenban"
cp -r files/kenban_os/images/* "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/data/default_images"
cp -r files/kenban_os/templates/* "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/data/default_templates"

install -m 664 files/kenban_os/pi-gen-files/.profile "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/.profile"
install -m 664 files/kenban_os/pi-gen-files/.xinitrc "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/.xinitrc"
install -m 644 files/kenban_os/pi-gen-files/websocket-sync.service "${ROOTFS_DIR}/etc/systemd/system/websocket-sync.service"
install -m 644 files/kenban_os/pi-gen-files/kenban-wifi-manager.service "${ROOTFS_DIR}/etc/systemd/system/kenban-wifi-manager.service"
install -m 644 files/kenban_os/pi-gen-files/kenbanxorg.conf "${ROOTFS_DIR}/etc/X11/xorg.conf.d/kenban.conf"

on_chroot << EOF
  
  raspi-config nonint do_boot_behaviour B2
  sed -i 's/sam/${FIRST_USER_NAME}/g' /etc/systemd/system/getty@tty1.service.d/autologin.conf
  systemctl enable websocket-sync.service kenban-wifi-manager.service

  pip install -r /home/${FIRST_USER_NAME}/kenban/requirements.txt

  chmod 755 /home/${FIRST_USER_NAME}/kenban/network/wifi-connect
  chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /home/${FIRST_USER_NAME}/kenban
  chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /home/${FIRST_USER_NAME}/data

  echo "$(( RANDOM % 60)) $(( RANDOM % 8)) $(( RANDOM % 30 + 1)) * * root ansible-pull -U https://github.com/kenban/kenban_os/ -C production" > /etc/cron.d/kenban-ansible-pull

EOF
