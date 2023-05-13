#!/bin/sh

set -e

if [ -z "$GH_TOKEN" ] || [ -z "$GH_MAIL" ] || [ -z "$GH_NAME" ] || [ -z "$DOCS_DIR" ] || [ -z "$BUILD_DIR" ]; then
  echo "Environment configuration missing, exiting... "
  exit 1
fi

TEMP_DIR="temp_$GITHUB_SHA"
REPO=$GITHUB_REPOSITORY
HTML_DIR="$BUILD_DIR/html/"

# Disable Safe Repository checks
git config --global --add safe.directory "/github/workspace"
git config --global --add safe.directory "/github/workspace/$TEMP_DIR"

# Clone repo with gh-pages branch
echo "Cloning gh-pages..."
git clone --branch gh-pages https://$GH_NAME:$GH_TOKEN@github.com/$REPO.git $TEMP_DIR

# Get commit message
message=$(git log -1 --format=%B)
echo "Message:"
echo $message

# Copy HTML files
echo "Copying files to gh-pages"
rsync -av $HTML_DIR $TEMP_DIR --exclude .git

# Set up credentials for Github Pages
cd $TEMP_DIR
git config user.name $GH_NAME
git config user.email $GH_MAIL

# Push to Github Pages
echo "Pushing to gh-pages"
git add .
git commit -m "$message"
git push origin gh-pages
