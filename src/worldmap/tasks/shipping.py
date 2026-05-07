#!/usr/bin/env python3
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
    """Haversine formula to calculate distance between two points."""
    R = 6371.0
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
        self.xplanet_settings = self.config.get_section("xplanet")

    def normalize_lon_for_bbox(self, lon, lon_min):
        """Shifts longitude into the 360-degree window starting at lon_min."""
        if lon is None: return None
        return (lon - lon_min) % 360 + lon_min

    def adjust_bbox_for_aspect_ratio(self, bbox, target_ratio=2.0):
        """Matches the bbox logic in renderer.py to ensure marker/map alignment."""
        lon_min, lat_min, lon_max, lat_max = bbox
        delta_lon = lon_max - lon_min
        delta_lat = lat_max - lat_min
        if delta_lat == 0: return bbox
        current_ratio = delta_lon / delta_lat

        if current_ratio < target_ratio:
            padding = (delta_lat * target_ratio - delta_lon) / 2
            lon_min -= padding
            lon_max += padding
        elif current_ratio > target_ratio:
            padding = (delta_lon / target_ratio - delta_lat) / 2
            lat_min -= padding
            lat_max += padding

        # Latitude Safety Caps
        if lat_max > 90:
            lat_min -= (lat_max - 90)
            lat_max = 90
        if lat_min < -90:
            lat_max += (-90 - lat_min)
            lat_min = -90

        return [lon_min, lat_min, lon_max, lat_max]

    async def run(self):
        self.config.load()
        self.exit_if_disabled()

        ship_db = ShipDatabase()
        map_region_name = self.xplanet_settings.get("region", fallback=None)
        expiry = self.settings.getint("expiry_days", fallback=7)

        # 1. Resolve and Adjust BBox (Mirroring renderer.py)
        bbox = None
        if map_region_name:
            if map_region_name.startswith("["):
                try:
                    bbox = [float(x) for x in json.loads(map_region_name)]
                except:
                    logger.error("Invalid BBox JSON")
            else:
                raw = ship_db.get_region_definition(map_region_name)
                if raw:
                    bbox = [float(raw['lon_min']), float(raw['lat_min']),
                            float(raw['lon_max']), float(raw['lat_max'])]

            if bbox:
                bbox = self.adjust_bbox_for_aspect_ratio(bbox, target_ratio=2.0)
                logger.info(f"Shipping normalization active for bbox: {bbox}")

        # 2. Setup Filters and Config
        show_tracks = self.settings.getboolean("show_tracks", fallback=False)
        track_min_dist = float(self.settings.get("track_min_distance_km", fallback=5.0))
        track_max_points = self.settings.getint("track_max_points", fallback=10)

        show_ships_underway = self.settings.getboolean("show_ships_underway", fallback=False)
        show_ship_icons = self.settings.get("show_ship_icons", fallback="")
        show_ship_classes = json.loads(self.settings.get("filter_show_ship_classes", fallback='["Tanker", "Cargo"]'))
        show_names_classes = json.loads(self.settings.get("filter_show_names_for_classes", fallback='["Tanker"]'))
        show_ships_by_name = json.loads(self.settings.get("filter_show_ships_by_name", fallback='[]'))
        min_length = self.settings.getint("filter_ships_minimum_length", fallback=0)
        base_label_fontsize = float(self.settings.getint("label_fontsize", fallback=12))
        label_color_default = self.settings.get("marker_color", fallback="red")

        fleet = ship_db.get_fleet(map_region_name, expiry_days=expiry)
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

                raw_lat, raw_lon = ship.get_vessel_position()
                if raw_lat is None or raw_lon is None:
                    continue

                # Colour logic
                ship_colour = ship.get_vessel_colour()
                marker_colour = ""

                # --- 3. Coordinate Normalization ---
                ship_latitude = raw_lat
                ship_longitude = raw_lon

                if bbox:
                    # Shift longitude to handle Date Line crossing (e.g. -179 becomes 181)
                    ship_longitude = self.normalize_lon_for_bbox(raw_lon, bbox[0])

                    # Geographic Cull: If ship is outside the ADJUSTED map, skip it
                    if not (bbox[1] <= ship_latitude <= bbox[3] and
                            bbox[0] <= ship_longitude <= bbox[2]):
                        continue

                # Formatting and Marker Writing
                ship_colour = ship.get_vessel_colour()
                ship_label = fontsize = marker_image = ""

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

                # --- 4. Track Normalization ---
                if show_tracks and ship.vessel_class in show_names_classes:
                    history = ship_db.get_ship_track(ship.mmsi, limit=100)
                    last_lat, last_lon = ship_latitude, ship_longitude
                    points_placed = 0

                    for pos in history:
                        if points_placed >= track_max_points: break

                        h_lat = float(pos['lat'])
                        h_lon = float(pos['lon'])

                        if bbox:
                            h_lon = self.normalize_lon_for_bbox(h_lon, bbox[0])

                        dist = get_distance_km(last_lat, last_lon, h_lat, h_lon)
                        if dist >= track_min_dist:
                            # Only write track points if they are within our bbox
                            if not bbox or (bbox[1] <= h_lat <= bbox[3] and bbox[0] <= h_lon <= bbox[2]):
                                f.write(f"{h_lat} {h_lon} color={label_color_default}\n")
                                last_lat, last_lon = h_lat, h_lon
                                points_placed += 1

        logger.info(f"Shipping update complete. Placed {written_count} ships in region.")