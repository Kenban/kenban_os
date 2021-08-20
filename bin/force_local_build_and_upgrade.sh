#!/bin/bash

# vim: tabstop=4 shiftwidth=4 softtabstop=4
# -*- sh-basic-offset: 4 -*-

set -euo pipefail

GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
GIT_SHORT_HASH=$(git rev-parse --short HEAD)
GIT_HASH=$(git rev-parse HEAD)

if [ "$GIT_BRANCH" = "master" ]; then
    DOCKER_TAG="latest"
else
    DOCKER_TAG="$GIT_BRANCH"
fi

if [ -n "${CROSS_COMPILE+x}" ]; then
    echo "Running with cross-compile using docker buildx..."
    DOCKER_BUILD_ARGS=("buildx" "build" "--push" "--platform" "linux/arm/v6,linux/arm/v7")
else
    echo "Running without cross-compile..."
    DOCKER_BUILD_ARGS=("build")
fi

#no cache
DOCKER_BUILD_ARGS+=("--no-cache")


docker pull balenalib/rpi-raspbian:buster

for container in base server celery redis nginx kbsync; do
    echo "Building $container"
    docker "${DOCKER_BUILD_ARGS[@]}" \
        --build-arg "GIT_HASH=$GIT_HASH" \
        --build-arg "GIT_SHORT_HASH=$GIT_SHORT_HASH" \
        --build-arg "GIT_BRANCH=$GIT_BRANCH" \
        -f "docker/Dockerfile.$container" \
        -t "kenban/kb-os-$container:$DOCKER_TAG" .
done

echo "Building viewer for different architectures..."
for pi_version in pi4 pi3; do
    echo "Building viewer container for $pi_version"
    docker "${DOCKER_BUILD_ARGS[@]}" \
        --build-arg "PI_VERSION=$pi_version" \
        --build-arg "GIT_HASH=$GIT_HASH" \
        --build-arg "GIT_SHORT_HASH=$GIT_SHORT_HASH" \
        --build-arg "GIT_BRANCH=$GIT_BRANCH" \
        -f docker/Dockerfile.viewer \
        -t "kenban/kb-os-viewer:$DOCKER_TAG-$pi_version" .
done

# Export various environment variables
export MY_IP=$(ip -4 route get 8.8.8.8 | awk {'print $7'} | tr -d '\n')
TOTAL_MEMORY_KB=$(grep MemTotal /proc/meminfo | awk {'print $2'})
export VIEWER_MEMORY_LIMIT_KB=$(echo "$TOTAL_MEMORY_KB" \* 0.7 | bc)

# Hard code this to latest for now.
export DOCKER_TAG="latest"

# Detect Raspberry Pi version
if grep -qF "Raspberry Pi 4" /proc/device-tree/model; then
    export DEVICE_TYPE="pi4"
elif grep -qF "Raspberry Pi 3" /proc/device-tree/model; then
    export DEVICE_TYPE="pi3"
elif grep -qF "Raspberry Pi 2" /proc/device-tree/model; then
    export DEVICE_TYPE="pi2"
else
    # This should not be used as an else statement but
    # let's leave in there for now.
    export DEVICE_TYPE="pi1"
fi

sudo -E docker-compose \
    -f /home/pi/screenly/docker-compose.yml \
    -f /home/pi/screenly/docker-compose.override.yml \
    up -d
