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

if [[ ( -n "${PUSH+x}" && -z "${CROSS_COMPILE+x}" ) ]]; then
        echo "Will push images when built"
fi

if [ -n "${CROSS_COMPILE+x}" ]; then
    echo "Running with cross-compile using docker buildx..."
    DOCKER_BUILD_ARGS=("buildx" "build" "--push" "--platform" "linux/arm/v6,linux/arm/v7")
else
    echo "Running without cross-compile..."
    DOCKER_BUILD_ARGS=("build")
fi

if [ -n "${CLEAN_BUILD+x}" ]; then
  echo "Running with no cache"
    DOCKER_BUILD_ARGS+=("--no-cache")
fi

docker pull balenalib/rpi-raspbian:buster

for image in base server celery redis nginx kbsync; do
    echo "Building $image"
    docker "${DOCKER_BUILD_ARGS[@]}" \
        --build-arg "GIT_HASH=$GIT_HASH" \
        --build-arg "GIT_SHORT_HASH=$GIT_SHORT_HASH" \
        --build-arg "GIT_BRANCH=$GIT_BRANCH" \
        -f "docker/Dockerfile.$image" \
        -t "kenban/$image-kos:$DOCKER_TAG" .

    # Push if the push flag is set and not cross compiling
    if [[ ( -n "${PUSH+x}" && -z "${CROSS_COMPILE+x}" ) ]]; then
        docker push "kenban/$image-kos:$DOCKER_TAG"
        docker push "kenban/$image-kos:latest"
    fi
done

echo "Building viewer for different architectures..."
for pi_version in pi4 pi3; do
    echo "Building viewer image for $pi_version"
    docker "${DOCKER_BUILD_ARGS[@]}" \
        --build-arg "PI_VERSION=$pi_version" \
        --build-arg "GIT_HASH=$GIT_HASH" \
        --build-arg "GIT_SHORT_HASH=$GIT_SHORT_HASH" \
        --build-arg "GIT_BRANCH=$GIT_BRANCH" \
        -f docker/Dockerfile.viewer \
        -t "kenban/viewer-kos:$DOCKER_TAG-$pi_version" .

    # Push if the push flag is set and not cross compiling
    if [[ ( -n "${PUSH+x}" && -z "${CROSS_COMPILE+x}" ) ]]; then
        docker push "kenban/viewer-kos:$DOCKER_TAG-$pi_version"
        docker push "kenban/viewer-kos:$DOCKER_TAG-latest"
    fi
done

