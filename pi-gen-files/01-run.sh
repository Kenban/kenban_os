#!/bin/bash -e

mkdir -p "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/data/default_images"
mkdir -p "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/data/default_templates"
mkdir -p "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/kenban"

cp -r files/kenban_os/* "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/kenban"

install -m 664 files/.profile "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/.profile"
install -m 664 files/.xinitrc "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/.xinitrc"


cp -r files/images/* "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/data/default_images"
cp -r files/templates/* "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/data/default_templates"

install -m 644 files/websocket-sync.service "${ROOTFS_DIR}/etc/systemd/system/websocket-sync.service"
install -m 644 files/kenban-wifi-manager.service "${ROOTFS_DIR}/etc/systemd/system/kenban-wifi-manager.service"

install -m 644 files/kenbanxorg.conf "${ROOTFS_DIR}/etc/X11/xorg.conf.d/kenban.conf"

on_chroot << EOF
  
  raspi-config nonint do_boot_behaviour B2
  sed -i 's/sam/pi/g' /etc/systemd/system/getty@tty1.service.d/autologin.conf
  
  systemctl enable websocket-sync.service kenban-wifi-manager.service

  pip install -r /home/${FIRST_USER_NAME}/kenban/requirements/requirements.txt

  chmod 755 /home/${FIRST_USER_NAME}/kenban/network/wifi-connect
  chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /home/${FIRST_USER_NAME}/kenban
  chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /home/${FIRST_USER_NAME}/data

  (crontab -l 2>/dev/null; echo "$(( RANDOM % 60)) $(( RANDOM % 8)) $(( RANDOM % 30 + 1)) * * ansible-pull -U https://github.com/kenban/kenban_os/ -C master") | crontab -

EOF
