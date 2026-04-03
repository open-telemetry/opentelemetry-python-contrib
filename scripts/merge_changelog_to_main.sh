#!/bin/bash

# This script copies release notes for the current version from CHANGELOG.md file
# and stores them in a temporary file for later use in the release workflow

# This script is called from the release workflows (package-release.yml and release.yml).

set -ev

if [[ -z $PRIOR_VERSION_WHEN_PATCH ]]; then
    # this was not a patch release, so the version exists already in the CHANGELOG.md

    # update the release date
    date=$(gh release view $RELEASE_TAG --json publishedAt --jq .publishedAt | sed 's/T.*//')
    sed -Ei "s/## Version ${VERSION}.*/## Version ${VERSION} ($date)/" ${CHANGELOG}

    # the entries are copied over from the release branch to support workflows
    # where change log entries may be updated after preparing the release branch

    # copy the portion above the release, up to and including the heading
    sed -n "0,/^## Version ${VERSION} ($date)/p" ${CHANGELOG} > /tmp/CHANGELOG.md

    # copy the release notes
    cat /tmp/CHANGELOG_SECTION.md >> /tmp/CHANGELOG.md

    # copy the portion below the release
    sed -n "0,/^## Version ${VERSION} /d;0,/^## Version /{/^## Version/!d};p" ${CHANGELOG} \
        >> /tmp/CHANGELOG.md

    # update the real CHANGELOG.md
    cp /tmp/CHANGELOG.md ${CHANGELOG}
else
    # this was a patch release, so the version does not exist already in the CHANGELOG.md

    # copy the portion above the top-most release, not including the heading
    sed -n "0,/^## Version /{ /^## Version /!p }" ${CHANGELOG} > /tmp/CHANGELOG.md

    # add the heading
    date=$(gh release view $RELEASE_TAG --json publishedAt --jq .publishedAt | sed 's/T.*//')
    echo "## Version ${VERSION} ($date)" >> /tmp/CHANGELOG.md

    # copy the release notes
    cat /tmp/CHANGELOG_SECTION.md >> /tmp/CHANGELOG.md

    # copy the portion starting from the top-most release
    sed -n "/^## Version /,\$p" ${CHANGELOG} >> /tmp/CHANGELOG.md

    # update the real CHANGELOG.md
    cp /tmp/CHANGELOG.md ${CHANGELOG}
fi