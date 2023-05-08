#!/bin/sh

set -e

if [ -z "$GH_TOKEN" ] || [ -z "$GH_MAIL" ] || [ -z "$GH_NAME" ]; then
  echo "Environment configuration missing, exiting... "
  exit 1
fi

TEMP_DIR="temp_$GITHUB_SHA"
REPO=$GITHUB_REPOSITORY
DOCS_DIR="docs/"

# Disable Safe Repository checks
git config --global --add safe.directory "/github/workspace"
git config --global --add safe.directory "/github/workspace/$TEMP_DIR"

# Clone wiki
echo "Cloning wiki..."
git clone https://$GH_NAME:$GH_TOKEN@github.com/$REPO.wiki.git $TEMP_DIR

# Get commit message
message=$(git log -1 --format=%B)
echo "Message:"
echo $message

# Copy files
echo "Copying files to Wiki"
rsync -av --delete $DOCS_DIR $TEMP_DIR/ --exclude .git --exclude-from "$DOCS_DIR/wiki_exclude"

# Setup credentials for wiki
cd $TEMP_DIR
git config user.name $GH_NAME
git config user.email $GH_MAIL

# Push to Wiki
echo "Pushing to Wiki"
git add .
git commit -m "$message"
git push origin master
