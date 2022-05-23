#!/bin/sh

# This file is a fork of GitHub Wiki Action plugin by Andrew Chen Wang
# https://github.com/Andrew-Chen-Wang/github-wiki-action

# This script assumes there is rsync and git installed in executing container.

if [ -z "$GH_TOKEN" ]; then
  echo "GH_TOKEN ENV is missing."
  exit 1
fi

if [ -z "$GH_MAIL" ]; then
  echo "GH_MAIL ENV is missing."
  exit 1
fi

if [ -z "$GH_NAME" ]; then
  echo "GH_NAME ENV is missing."
  exit 1
fi

TEMP_CLONE_FOLDER="temp_wiki_$GITHUB_SHA"
REPO=$GITHUB_REPOSITORY
WIKI_DIR="docs/"

# Disable Safe Repository checks
git config --global --add safe.directory "/github/workspace"
git config --global --add safe.directory "/github/workspace/$TEMP_CLONE_FOLDER"

# Clone wiki
echo "Cloning wiki git..."
git clone https://$GH_NAME:$GH_TOKEN@github.com/$REPO.wiki.git $TEMP_CLONE_FOLDER

# Get commit message
message=$(git log -1 --format=%B)
echo "Message:"
echo $message

# Copy files
echo "Copying files to Wiki"
rsync -av --delete $WIKI_DIR $TEMP_CLONE_FOLDER/ --exclude .git

# Setup credentials for wiki
cd $TEMP_CLONE_FOLDER
git config user.name $GH_NAME
git config user.email $GH_MAIL

# Push to Wiki
echo "Pushing to Wiki"
git add .
git commit -m "$message"
git push origin master
