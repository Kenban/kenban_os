#!/bin/bash

mkdir -p \
    /data/.config \
    /data/.kenban \
    /data/kenban_assets

cp -n /usr/src/app/ansible/roles/kenban/files/kenban.conf /data/.kenban/kenban.conf
cp -n /usr/src/app/ansible/roles/kenban/files/default_assets.yml /data/.kenban/default_assets.yml
cp -n /usr/src/app/ansible/roles/kenban/files/kenban.db /data/.kenban/kenban.db

if [ -n "${OVERWRITE_CONFIG}" ]; then
    echo "Requested to overwrite Kenban config file."
    cp /usr/src/app/ansible/roles/kenban/files/kenban.conf "/data/.kenban/kenban.conf"
fi

# Set management page's user and password from environment variables,
# but only if both of them are provided. Can have empty values provided.
if [ -n "${MANAGEMENT_USER+x}" ] && [ -n "${MANAGEMENT_PASSWORD+x}" ]; then
    sed -i -e "s/^user=.*/user=${MANAGEMENT_USER}/" -e "s/^password=.*/password=${MANAGEMENT_PASSWORD}/" /data/.kenban/kenban.conf
fi

python3 websocket.py
