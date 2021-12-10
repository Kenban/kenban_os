#!/bin/bash -e

# vim: tabstop=4 shiftwidth=4 softtabstop=4
# -*- sh-basic-offset: 4 -*-

WEB_UPGRADE=false
BRANCH_VERSION=
UPGRADE_SYSTEM=

if [ -f .env ]; then
  source .env
fi



# clear screen
clear

export DOCKER_TAG="latest"
BRANCH="master"

echo && read -p "Would you like to perform a full system upgrade? (y/N)" -n 1 -r -s UPGRADE && echo
if [ "$UPGRADE" != 'y' ]; then
  EXTRA_ARGS=("--skip-tags" "system-upgrade")
fi

REPOSITORY=https://github.com/kenban/kenban_os.git

sudo mkdir -p /etc/ansible
echo -e "[local]\nlocalhost ansible_connection=local" | sudo tee /etc/ansible/hosts >/dev/null

if [ ! -f /etc/locale.gen ]; then
  # No locales found. Creating locales with default UK/US setup.
  echo -e "en_GB.UTF-8 UTF-8\nen_US.UTF-8 UTF-8" | sudo tee /etc/locale.gen >/dev/null
  sudo locale-gen
fi

# sam commented this out because apt was failing
#sudo sed -i 's/apt.screenlyapp.com/archive.raspbian.org/g' /etc/apt/sources.list
sudo apt update -y
sudo apt-get purge -y \
  python3-pyasn1
sudo apt-get install -y --no-install-recommends \
  git \
  libffi-dev \
  libssl-dev \
  python3-pip \
  python3-setuptools \
  python3-wheel \
  whois

# Install Ansible from requirements file.
if [ "$BRANCH" = "master" ]; then
  ANSIBLE_VERSION=$(curl -s https://raw.githubusercontent.com/Kenban/kenban_os/$BRANCH/requirements/requirements.host.txt | grep ansible)
else
  ANSIBLE_VERSION=ansible==2.8.8
fi

sudo pip install "$ANSIBLE_VERSION"

sudo -u pi ansible localhost \
  -m git \
  -a "repo=$REPOSITORY dest=/home/pi/kenban version=$BRANCH force=no"
cd /home/pi/kenban/ansible

sudo -E ansible-playbook site.yml "${EXTRA_ARGS[@]}"

# Pull down and install containers
/home/pi/kenban/bin/upgrade_containers.sh

sudo apt-get autoclean
sudo apt-get clean
sudo docker system prune -f
sudo apt autoremove -y
sudo apt-get install plymouth --reinstall -y
sudo find /usr/share/doc \
  -depth \
  -type f \
  ! -name copyright \
  -delete
sudo find /usr/share/doc \
  -empty \
  -delete
sudo rm -rf \
  /usr/share/man \
  /usr/share/groff \
  /usr/share/info/* \
  /usr/share/lintian \
  /usr/share/linda /var/cache/man
sudo find /usr/share/locale \
  -type f \
  ! -name 'en' \
  ! -name 'de*' \
  ! -name 'es*' \
  ! -name 'ja*' \
  ! -name 'fr*' \
  ! -name 'zh*' \
  -delete
sudo find /usr/share/locale \
  -mindepth 1 \
  -maxdepth 1 \
  ! -name 'en*' \
  ! -name 'de*' \
  ! -name 'es*' \
  ! -name 'ja*' \
  ! -name 'fr*' \
  ! -name 'zh*' \
  ! -name 'locale.alias' \
  -exec rm -r {} \;

sudo chown -R pi:pi /home/pi
sudo chmod 755 /home/pi/kenban/network/wifi-connect

# Run sudo w/out password
if [ ! -f /etc/sudoers.d/010_pi-nopasswd ]; then
  echo "pi ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/010_pi-nopasswd >/dev/null
  sudo chmod 0440 /etc/sudoers.d/010_pi-nopasswd
fi

# Ask user to set a new pi password if default password "raspberry" detected
check_defaultpw() {
  if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "production" ]; then
    set +x

    # currently only looking for $6$/sha512 hash
    local VAR_CURRENTPISALT
    local VAR_CURRENTPIUSERPW
    local VAR_DEFAULTPIPW
    VAR_CURRENTPISALT=$(sudo cat /etc/shadow | grep pi | awk -F '$' '{print $3}')
    VAR_CURRENTPIUSERPW=$(sudo cat /etc/shadow | grep pi | awk -F ':' '{print $2}')
    VAR_DEFAULTPIPW=$(mkpasswd -m sha-512 raspberry "$VAR_CURRENTPISALT")

    if [[ "$VAR_CURRENTPIUSERPW" == "$VAR_DEFAULTPIPW" ]]; then
      echo "Warning: The default Raspberry Pi password was detected!"
      read -p "Do you still want to change it? (y/N)" -n 1 -r -s PWD_CHANGE
      if [ "$PWD_CHANGE" = 'y' ]; then
        set +e
        passwd
        set -ex
      fi
    else
      echo "The default raspberry pi password was not detected, continuing with installation..."
      set -x
    fi
  fi
}

check_defaultpw

echo -e "Kenban version: $(git rev-parse --abbrev-ref HEAD)@$(git rev-parse --short HEAD)\n$(lsb_release -a)" >~/version.md

set +x

echo "Installation completed."
read -p "You need to reboot the system for the installation to complete. Would you like to reboot now? (y/N)" -n 1 -r -s REBOOT && echo
if [ "$REBOOT" == 'y' ]; then
  sudo reboot
fi
