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

# Export various environment variables
export MY_IP=$(ip -4 route get 8.8.8.8 | awk {'print $7'} | tr -d '\n')
TOTAL_MEMORY_KB=$(grep MemTotal /proc/meminfo | awk {'print $2'})
export VIEWER_MEMORY_LIMIT_KB=$(echo "$TOTAL_MEMORY_KB" \* 0.7 | bc)

# Hard code this to latest for now.
export DOCKER_TAG="latest"

docker pull balenalib/rpi-raspbian:buster

for container in kbsync; do
    echo "Building $container"
    docker "${DOCKER_BUILD_ARGS[@]}" \
        --build-arg "GIT_HASH=$GIT_HASH" \
        --build-arg "GIT_SHORT_HASH=$GIT_SHORT_HASH" \
        --build-arg "GIT_BRANCH=$GIT_BRANCH" \
        -f "docker/Dockerfile.$container" \
        -t "kenban/kb-os-$container:$DOCKER_TAG" .
done


sudo -E docker-compose \
    -f /home/pi/kenban/docker-compose.yml \
    -f /home/pi/kenban/docker-compose.override.yml \
    up -d
