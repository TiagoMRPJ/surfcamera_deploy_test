#!/bin/bash

# Path to your repository

git config --global --replace-all safe.directory /home/idmind/surfcamera_deploy_test

GIT_REPO="git@github.com:TiagoMRPJ/surfcamera_deploy_test.git"

cd /home/idmind/surfcamera_deploy_test

# Fetch updates from remote
git fetch origin main

# Check if local main differs from remote main
LOCAL=$(git rev-parse main)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Updates found! Pulling and rebooting... "
    git reset --hard origin/main
    sudo reboot -h now
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - No updates. Continuing..."
fi
