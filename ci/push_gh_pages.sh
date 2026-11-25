#!/usr/bin/env sh

set -e

if [ -z "$GH_TOKEN" ] || [ -z "$DOCS_DIR" ] || [ -z "$BUILD_DIR" ]; then
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
git clone --branch gh-pages https://x-access-token:$GH_TOKEN@github.com/$REPO.git $TEMP_DIR

# Get commit message and author
message=$(git log -1 --format=%B)
author_name=$(git log -1 --format=%an)
author_mail=$(git log -1 --format=%ae)
echo "Message:"
echo $message

# Copy HTML files
echo "Copying files to gh-pages"
rsync -av $HTML_DIR $TEMP_DIR --exclude .git

# Set up credentials for Github Pages
cd $TEMP_DIR
git config user.name "$author_name"
git config user.email "$author_mail"

# Push to Github Pages
echo "Pushing to gh-pages"
git add .
git commit -m "$message"
git push origin gh-pages
