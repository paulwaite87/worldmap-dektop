#!/bin/bash
set -e

# Set up vars
source ./config/common.conf

# Add one of these to get a one-time-only refresh of the wallpaper
if [ "$1" == "-once" -o "$1" == "--once" ] ; then
  update_opt="--once"
else
  update_opt=
fi

# Update cloud map
${PYTHON3} wallpaper_update_daemon.py ${update_opt} --directory=${DATA} --suffix="worldmap.jpg"
