#!/bin/bash

REPO_URL="git@github.com:idmind-robotics/surf_camera.git"
LOCAL_DIR="/home/idmind/surf_camera"
BRANCH="main"
LOG_FILE=/home/idmind/surf_camera/logs/githublog.txt

update_repo() {
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    
    if [ ! -d "$LOCAL_DIR" ]; then
        echo "[$TIMESTAMP] Local repository not found. Cloning..." | tee -a "$LOG_FILE"
        git clone "$REPO_URL" "$LOCAL_DIR" 2>&1 | tee -a "$LOG_FILE"
        echo "[$TIMESTAMP] Clone completed." | tee -a "$LOG_FILE"
    else
        echo "[$TIMESTAMP] Checking for updates in local repository..." #| tee -a "$LOG_FILE"
        cd "$LOCAL_DIR" || exit
        UPDATES=$(git fetch origin "$BRANCH" && git diff --name-only "origin/$BRANCH")
        if [ -n "$UPDATES" ]; then
            git reset --hard "origin/$BRANCH" 2>&1 | tee -a "$LOG_FILE"
            echo "[$TIMESTAMP] Local Repository updated successfully." | tee -a "$LOG_FILE"
        else
            echo "[$TIMESTAMP] Repository is already up to date." #| tee -a "$LOG_FILE"
        fi
    fi
}

update_repo
