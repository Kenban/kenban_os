#!/bin/bash

mkdir -p \
    /data/.config \
    /data/.kenban \
    /data/kenban_assets/kenban_templates \
    /data/kenban_assets/kenban_images

cp -n /usr/src/app/ansible/roles/kenban/files/kenban.conf /data/.kenban/kenban.conf
cp -n /usr/src/app/ansible/roles/kenban/files/default_assets.yml /data/.kenban/default_assets.yml
cp -n /usr/src/app/ansible/roles/kenban/files/kenban.db /data/.kenban/kenban.db

if [ -n "${OVERWRITE_CONFIG}" ]; then
    echo "Requested to overwrite config file."
    cp /usr/src/app/ansible/roles/kenban/files/kenban.conf "/data/.kenban/kenban.conf"
fi

python3 server.py
