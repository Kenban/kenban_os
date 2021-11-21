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

if [ -n "${CLEAN_BUILD+x}" ]; then
    DOCKER_BUILD_ARGS+=("--no-cache")
fi

echo "Removing kenban_server_1"
docker stop kenban_server_1
docker rm kenban_server_1
#docker image rm kenban/server-kos:$DOCKER_TAG

docker pull balenalib/rpi-raspbian:buster

echo "Building server"
docker "${DOCKER_BUILD_ARGS[@]}" \
    --build-arg "GIT_HASH=$GIT_HASH" \
    --build-arg "GIT_SHORT_HASH=$GIT_SHORT_HASH" \
    --build-arg "GIT_BRANCH=$GIT_BRANCH" \
    -f "docker/Dockerfile.server" \
    -t "kenban/server-kos:$DOCKER_TAG" .

# Push if the push flag is set and not cross compiling
if [[ ( -n "${PUSH+x}" && -z "${CROSS_COMPILE+x}" ) ]]; then
    docker push "kenban/server-kos:$DOCKER_TAG"
    docker push "kenban/server-kos:latest"
fi

bash ./bin/upgrade_containers.sh



