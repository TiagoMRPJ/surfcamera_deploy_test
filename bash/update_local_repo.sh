#!/bin/bash

# Path to your repository

GIT_REPO="git@github.com:TiagoJesusmrp/yourrepo.git"

# Fetch updates from remote
git fetch origin main

# Check if local main differs from remote main
LOCAL=$(git rev-parse main)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "Updates found! Pulling and rebooting..."
    git reset --hard origin/main
    sudo reboot -h now
else
    echo "No updates. Continuing..."
fi