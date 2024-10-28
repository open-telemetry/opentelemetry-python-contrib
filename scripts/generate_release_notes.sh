#!/bin/bash

# This script copies release notes for the current version from CHANGELOG.md file
# and stores them in /tmp/release-notes.txt.
# It also stores them in a /tmp/CHANGELOG_SECTION.md which is used later to copy them over to the
# CHANGELOG in main branch which is done by merge_changelog_to_main script.

# This script is called from the release workflows (package-release.yml and release.yml).

set -ev

# conditional block not indented because of the heredoc
if [[ ! -z $PRIOR_VERSION_WHEN_PATCH ]]; then
cat > /tmp/release-notes.txt << EOF
This is a patch release on the previous $PRIOR_VERSION_WHEN_PATCH release, fixing the issue(s) below.

EOF
fi

# CHANGELOG_SECTION.md is also used at the end of the release workflow
# for copying the change log updates to main
sed -n "0,/^## Version ${VERSION}/d;/^## Version /q;p" $CHANGELOG > /tmp/CHANGELOG_SECTION.md

# the complex perl regex is needed because markdown docs render newlines as soft wraps
# while release notes render them as line breaks
perl -0pe 's/(?<!\n)\n *(?!\n)(?![-*] )(?![1-9]+\. )/ /g' /tmp/CHANGELOG_SECTION.md >> /tmp/release-notes.txt
