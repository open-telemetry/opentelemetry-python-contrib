#!/bin/sh

# This script builds wheels for the API, SDK, and extension packages in the
# dist/ dir, to be uploaded to PyPI.

set -ev

# Get the latest versions of packaging tools
python3 -m pip install --upgrade pip build setuptools wheel

BASEDIR=$(dirname "$(readlink -f "$(dirname $0)")")
DISTDIR=dist

(
  cd $BASEDIR
  mkdir -p $DISTDIR
  rm -rf ${DISTDIR:?}/*

 for d in exporter/*/ opentelemetry-instrumentation/ opentelemetry-contrib-instrumentations/ opentelemetry-distro/ instrumentation/*/ processor/*/ propagator/*/ resource/*/ sdk-extension/*/ util/*/ ; do
   (
     echo "building $d"
     cd "$d"
     # Some ext directories (such as docker tests) are not intended to be
     # packaged. Verify the intent by looking for a pyproject.toml.
     if [ -f pyproject.toml ]; then
      python3 -m build --outdir "$BASEDIR/dist/"
     fi
   )
 done

 (
   cd $DISTDIR
   for x in * ; do
    # FIXME: Remove this once opentelemetry-resource-detector-azure package goes 1.X
    if echo "$x" | grep -Eq "^opentelemetry_(resource_detector_azure|util_genai).*(\.tar\.gz|\.whl)$"; then
      echo "Skipping $x because of manual upload by Azure maintainers."
      rm $x
    # NOTE: We filter beta vs 1.0 package at this point because we can read the
    # version directly from the .tar.gz/whl file
    elif echo "$x" | grep -Eq "^opentelemetry_.*-0\..*(\.tar\.gz|\.whl)$"; then
      :
    else
      echo "Skipping $x because it is not in pre-1.0 state and should be released using a tag."
      rm $x
    fi
   done
 )
)
