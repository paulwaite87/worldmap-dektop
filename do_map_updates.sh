#!/bin/bash
set -e

# NOTE: Each of the updaters below can be enabled or disabled in the
# appropriate section of config/worldmap.conf.

# Set up common vars
source ./config/common.conf

echo "Beginning map refresh"

# Update cloud map
# See [clouds] section in config/worldmap.conf
${PYTHON3} ${SCRIPTS}/update_clouds --config=${WORLDMAP_CONFIG_FILE}

# Update isobars image
# See [isobars] section in config/worldmap.conf
${PYTHON3} ${SCRIPTS}/update_isobars --config=${WORLDMAP_CONFIG_FILE}

# Overlay isobars image onto clouds image, create new composite image
# See [isobars] and [clouds] sections in config/worldmap.conf
${PYTHON3} ${SCRIPTS}/update_composite_image --config=${WORLDMAP_CONFIG_FILE}

# Grab active storm systems
# See [storms] section in config/worldmap.conf
${PYTHON3} ${SCRIPTS}/update_storms --config=${WORLDMAP_CONFIG_FILE}

# Grab recent earthquakes
# See [quakes] section in config/worldmap.conf
${PYTHON3} ${SCRIPTS}/update_quakes --config=${WORLDMAP_CONFIG_FILE}

# Grab shipping data
# See [shipping] section in config/worldmap.conf
${PYTHON3} ${SCRIPTS}/update_shipping --config=${WORLDMAP_CONFIG_FILE}

# Grab known volcanoes
# See [volcanoes] section in config/worldmap.conf
${PYTHON3} ${SCRIPTS}/update_volcanoes --config=${WORLDMAP_CONFIG_FILE}

# Run XPlanet to render the final World Map image
${PYTHON3} ${SCRIPTS}/run_xplanet --config=${WORLDMAP_CONFIG_FILE}

echo "Finished"
