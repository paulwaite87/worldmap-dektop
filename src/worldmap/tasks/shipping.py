#!/usr/bin/env python3
import os
import json
import logging
import asyncio
import math

# Internal library imports
from worldmap.lib.config import WorldMapConfig
from worldmap.lib.shipping import (
    ShipDatabase,
    Ship,
)
from .common import Updater

logger = logging.getLogger(__name__)


def get_distance_km(lat1, lon1, lat2, lon2):
    """
    Haversine formula to calculate the great-circle distance between two points
    on a sphere given their longitudes and latitudes.
    """
    R = 6371.0  # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class ShippingUpdater(Updater):
    def __init__(self, config: WorldMapConfig):
        super().__init__(config, "Shipping")
        self.set_output_path()

    async def run(self):
        self.config.load()  # Refresh config
        self.exit_if_disabled()

        ship_db = ShipDatabase()

        region_list = json.loads(self.settings.get("regions", fallback="[]"))
        expiry = self.settings.getint("expiry_days", fallback=3)

        # Track Settings
        show_tracks = self.settings.getboolean("show_tracks", fallback=False)
        track_min_dist = float(self.settings.get("track_min_distance_km", fallback=5.0))
        track_max_points = self.settings.getint("track_max_points", fallback=10)

        logger.debug(f"Generating map for regions: {region_list or 'GLOBAL'} (Expiry: {expiry} days)")

        fleet = ship_db.get_fleet(region_labels=region_list, expiry_days=expiry)

        # Filter and Format Markers
        show_ships_underway = self.settings.getboolean("show_ships_underway", fallback=False)
        show_ship_icons = self.settings.get("show_ship_icons", fallback="")
        show_ship_classes = json.loads(
            self.settings.get("filter_show_ship_classes", fallback='["Tanker", "Cargo"]')
        )
        show_names_classes = json.loads(
            self.settings.get("filter_show_names_for_classes", fallback='["Tanker"]')
        )
        show_ships_by_name = json.loads(
            self.settings.get("filter_show_ships_by_name", fallback='[]')
        )
        min_length = self.settings.getint("filter_ships_minimum_length", fallback=0)

        label_color_default = self.settings.get("marker_color", fallback="red")
        base_label_fontsize = float(self.settings.getint("label_fontsize", fallback=12))

        written_count = 0
        with open(self.output_path, "w") as f:
            for vessel in fleet:
                ship = Ship(vessel)

                # Length Filter
                ship_length, ship_beam = ship.get_vessel_dimensions()
                if ship_length < min_length:
                    continue

                # Class Filter
                if show_ship_classes and ship.vessel_class not in show_ship_classes:
                    continue

                # Names filter
                if show_ships_by_name and ship.vessel_name not in show_ships_by_name:
                    continue

                # Ship underway filter
                if show_ships_underway and not ship.is_underway():
                    continue

                # Formatting coordinates for Xplanet
                ship_latitude, ship_longitude = ship.get_vessel_position()
                if ship_latitude is None or ship_longitude is None:
                    continue

                # Colour logic
                ship_colour = ship.get_vessel_colour()
                marker_colour = ""

                # Ship label logic
                if ship.vessel_class in show_names_classes:
                    fontsize = int(base_label_fontsize)
                    ship_expanded_class = ship.get_expanded_vessel_class()

                    if ship_expanded_class == "ULTRA":
                        fontsize = int(base_label_fontsize * 2.0)
                    elif ship_expanded_class == "VLCC":
                        fontsize = int(base_label_fontsize * 1.6)
                    elif ship_expanded_class == "STD":
                        fontsize = int(base_label_fontsize * 1.3)

                    ship_label = f"{ship.get_vessel_description()}"
                    fontsize = f" fontsize={fontsize}"
                    marker_colour = f" color={ship_colour}"
                else:
                    ship_label = fontsize = ""

                # Ship icon image logic
                if show_ship_icons == "Arrows":
                    logger.debug("showing ships as arrow icons")
                    marker_image = f"image={ship.get_vessel_directional_icon()}"
                elif show_ship_icons == "Discs":
                    logger.debug("showing ships as disc icons")
                    marker_image = f" image={ship.get_vessel_disc_icon()}"
                else:
                    marker_image = ""
                    marker_colour = f" color={ship_colour}"
                    logger.debug("showing ships as default markers")


                # --- Write the Primary Ship Marker ---
                logger.debug(f'Ship: {ship_latitude} {ship_longitude} "{ship_label}"{fontsize}{marker_colour}{marker_image}')
                f.write(f'{ship_latitude} {ship_longitude} "{ship_label}"{fontsize}{marker_colour}{marker_image}\n')
                written_count += 1

                # --- Write Track Markers ---
                # Rule 1: No marker for latest position is handled by starting distance
                # check from current ship_latitude/longitude.
                if show_tracks and ship.vessel_class in show_names_classes:
                    # Fetch history (limited to 100 to ensure we find enough distant points)
                    history = ship_db.get_ship_track(ship.mmsi, limit=100)

                    last_lat, last_lon = ship_latitude, ship_longitude
                    points_placed = 0

                    for pos in history:
                        # Rule 3: Return a maximum of M markers
                        if points_placed >= track_max_points:
                            break

                        h_lat, h_lon = float(pos['lat']), float(pos['lon'])
                        dist = get_distance_km(last_lat, last_lon, h_lat, h_lon)

                        # Rule 2: Skip markers less than N kilometres from last marker
                        if dist >= track_min_dist:
                            f.write(f"{h_lat} {h_lon} color={label_color_default}\n")

                            last_lat, last_lon = h_lat, h_lon
                            points_placed += 1

        logger.debug(f"Shipping update complete. Updated {written_count} ships.")


def main():
    import argparse
    from worldmap.lib.logging import setup_logging

    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config = WorldMapConfig(args.config)
    updater = ShippingUpdater(config)
    asyncio.run(updater.run())


if __name__ == "__main__":
    main()