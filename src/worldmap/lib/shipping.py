import os
import math
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logger = logging.getLogger(__name__)

SPECIAL_VESSEL_TYPES = {
    0: "Vessel",
    30: "Fishing Vessel",
    31: "Towing Vessel",
    32: "Towing (Large/Towed)",
    33: "Dredging/Underwater Ops",
    34: "Diving Ops",
    35: "Military Ops",
    36: "Sailing Vessel",
    37: "Pleasure Craft",
    50: "Pilot Vessel",
    51: "Search and Rescue (SAR)",
    52: "Tug",
    53: "Port Tender",
    54: "Anti-Pollution Equipment",
    55: "Law Enforcement",
    58: "Medical Transport",
    59: "Non-Combatant (Neutral State)",
}

VESSEL_CLASSES = {
    1: "WIG (Wing In Ground)",
    2: "WIG (Wing In Ground)",
    4: "High Speed Craft",
    6: "Passenger",
    7: "Cargo",
    8: "Tanker",
    9: "Other",
}

VESSEL_SUBCLASSES = {
    1: " HazA",
    2: " HazB",
    3: " HazC",
    4: " HazD"
}


class Ship:
    def __init__(self, vessel):
        self.vessel = vessel

        # mmsi
        self.mmsi = vessel.get("mmsi")

        # name
        name = vessel.get("name") or "Unknown"
        self.vessel_name = name.replace('"', "").strip()

        # type
        self.vessel_type = vessel.get("vessel_type") or 0

        # class
        if self.vessel_type in SPECIAL_VESSEL_TYPES:
            self.vessel_class =  SPECIAL_VESSEL_TYPES[self.vessel_type]
        else:
            class_digit = int(self.vessel_type // 10)
            self.vessel_class = VESSEL_CLASSES.get(class_digit, f"Vessel (Type {self.vessel_type})")

        # subclass
        sub_digit = self.vessel_type % 10
        self.vessel_subclass = VESSEL_SUBCLASSES.get(sub_digit, "")

    def get_expanded_vessel_class(self):
        """
        Expands the standard vessel classes to a more descriptive string, but
        only for Tankers and Passenger ships.
        Args:
            vessel: The vessel to find the expanded class for

        Returns: String expanded class, or the default standard class
        """
        length, beam = self.get_vessel_dimensions()

        # Deal with bogus beam data
        if beam > 70:
            beam = 0

        # Ships like the BOREAS (WTIV) have a length-to-beam ratio < 3.
        # Normal tankers/cargo are usually 5:1 or 6:1.
        if self.vessel_class == "Tanker":
            if length > 0 and beam > 0 and (length / beam) < 3.5:
                return "SPEC"
            elif length > 350 and beam > 58:
                return "ULTRA"
            elif length > 300:
                return "VLCC"
            elif length >= 220:
                return "STD"
            else:
                return self.vessel_class

        elif self.vessel_class == "Passenger":
            if length > 250:
                return "Mega Cruise"  # Floating shopping mall/theme park
            elif length > 190:
                return "Cruise"  # Standard Cruise Ship
            elif length > 50:
                return "Ferry"  # Small / Large Ferry
            else:
                return self. vessel_class

        return self.vessel_class

    def get_vessel_dimensions(self):
        length = int(self.vessel.get("length") or 0)
        beam = int(self.vessel.get("beam") or 0)
        return length, beam

    def get_vessel_navigational_status(self):
        cog = float(self.vessel.get("cog") or 0.0)
        sog = float(self.vessel.get("sog") or 0.0)
        nav_status = int(self.vessel.get("nav_status") or 1)
        return cog, sog, nav_status

    def get_vessel_position(self):
        lat = self.vessel.get("lat")
        lon = self.vessel.get("lon")
        return (float(lat) if lat is not None else None,
                float(lon) if lon is not None else None)

    def get_vessel_heading_str(self):
        """
        Converts Course Over Ground (COG) into a cardinal direction string.
        """
        cog, _, _ = self.get_vessel_navigational_status()

        # Normalize COG to be within [0, 360)
        cog = cog % 360

        # Define the 8 cardinal directions in order
        directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

        # Each sector is 45 degrees. We add 22.5 to 'center' the
        # first sector (North) around 0 degrees.
        index = int((cog + 22.5) // 45)

        # Use modulo 8 to wrap 337.5 - 360 back to index 0 (North)
        return directions[index % 8]

    def get_vessel_directional_icon(self):
        """Returns what is essentially the filename of the icon eg. 'red_ship_NW.png'"""
        vessel_heading = self.get_vessel_heading_str()
        if self.vessel_class == "Tanker":
            icon_colour = "red"
        elif self.vessel_class == "Cargo":
            icon_colour = "green"
        else:
            icon_colour = "purple"
        return f"{icon_colour}_ship_{vessel_heading}.png"

    def get_vessel_disc_icon(self):
        suffix = "_empty.png" if self.is_unloaded() else ".png"
        if self.vessel_class == "Tanker":
            return f"ship_tanker{suffix}"
        elif self.vessel_class == "Cargo":
            return f"ship_cargo{suffix}"
        else:
            return f"ship{suffix}"

    def get_vessel_description(self):
        """This function returns the vessel description which starts with the
        name of the ship and then the class and subclass information"""
        return f"{self.vessel_name} {self.vessel_class}{self.vessel_subclass}"

    def get_vessel_colour(self):
        ship_expanded_class = self.get_expanded_vessel_class()
        if ship_expanded_class == "ULTRA":
            return "DeepPink"
        elif ship_expanded_class == "VLCC":
            return "Red"
        else:
            if self.vessel_class == "Cargo":
                return "Green"
            elif self.vessel_class == "Passenger":
                return "Purple"
            else:
                return "Yellow"

    def is_unloaded(self):
        """Determine whether a ship has been unloaded partially or fully"""
        current_draught = float(self.vessel.get("draught") or 0.0)
        draught_threshold = float(self.vessel.get("prev_draught") or 0.0) * 0.9
        return  0.0 < current_draught < draught_threshold > 0.0

    def is_underway(self) -> bool:
        """
        Returns True if vessel is moving faster than 1 knot
        and is not anchored (1) or moored (5).
        """
        # 0 = Under way using engine, 8 = Under way sailing
        # 1 = Anchored, 5 = Moored
        cog, sog, nav_status = self.get_vessel_navigational_status()
        return sog > 1.0 and nav_status not in [1, 5]


class ShipDatabase:
    def __init__(self):
        # We fetch variables and provide defaults just in case
        db_user = os.getenv("PGUSER", "wmap")
        db_pass = os.getenv("PGPASSWORD", "wmap")
        db_name = os.getenv("PGDATABASE", "worldmap")
        db_host = os.getenv("PGHOST", "worldmap_db")
        db_port = os.getenv("PGPORT", "5432")

        try:
            self.conn = psycopg2.connect(
                user=db_user,
                password=db_pass,
                dbname=db_name,
                host=db_host,
                port=db_port,
                cursor_factory=RealDictCursor
            )
            self.conn.autocommit = True
        except Exception as e:
            logger.error(f"Postgres Connection Failed: {e}")
            raise

    def update_ship_static_data(self, mmsi, metadata, body):
        """Processes ShipStaticData and UPSERTs into the ships table."""
        name = metadata.get("ShipName", "Unknown").strip()
        v_type = body.get("Type", 0)
        imo = body.get("ImoNumber", 0)
        callsign = body.get("CallSign", "").strip()
        draught = float(body.get("MaximumStaticDraught", 0.0))

        # Handle Dimension Math (AIS gives offsets A, B, C, D)
        dim = body.get("Dimension", {})
        length = int(dim.get("A", 0)) + int(dim.get("B", 0))
        beam = int(dim.get("C", 0)) + int(dim.get("D", 0))

        sql = """
              INSERT INTO ships (mmsi, name, vessel_type, imo, callsign, draught, prev_draught, length, beam)
              VALUES (%s, %s, %s, %s, %s, %s, 0.0, %s, %s) ON CONFLICT (mmsi) DO \
              UPDATE SET
                  prev_draught = CASE \
                  WHEN ships.draught != EXCLUDED.draught AND EXCLUDED.draught > 0 \
                  THEN ships.draught \
                  ELSE ships.prev_draught
              END \
              ,
                name = EXCLUDED.name,
                vessel_type = EXCLUDED.vessel_type,
                imo = EXCLUDED.imo,
                callsign = EXCLUDED.callsign,
                draught = EXCLUDED.draught,
                length = EXCLUDED.length,
                beam = EXCLUDED.beam; \
              """
        with self.conn.cursor() as cur:
            cur.execute(sql, (str(mmsi), name, v_type, imo, callsign, draught, length, beam))

    def update_ship_position_data(self, mmsi, body):
        lat = body.get("Latitude")
        lon = body.get("Longitude")
        nav_status = body.get("NavigationalStatus", 0)
        cog = body.get("Cog", 0.0)
        sog = body.get("Sog", 0.0)

        # Ensure the ship exists in the 'ships' table first (Shadow Insert)
        # This prevents Foreign Key violations in the history table.
        sql_ensure_ship = """
                          INSERT INTO ships (mmsi, name, vessel_type)
                          VALUES (%s, 'Unknown', 0) ON CONFLICT (mmsi) DO NOTHING; \
                          """

        # Update current ship status
        sql_live = """
                   UPDATE ships
                   SET lat                  = %s,
                       lon                  = %s,
                       geom                 = ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                       nav_status           = %s,
                       cog                  = %s,
                       sog                  = %s,
                       last_position_update = NOW()
                   WHERE mmsi = %s; \
                   """

        # Insert historical track
        sql_history = """
                      INSERT INTO ship_position (mmsi, lat, lon, geom, sog, cog, nav_status, acquired_at)
                      VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, NOW());
                      """
        try:
            with self.conn.cursor() as cur:
                # Step 1: Guarantee the parent record exists
                cur.execute(sql_ensure_ship, (str(mmsi),))

                # Step 2: Update live position
                cur.execute(sql_live, (lat, lon, lon, lat, nav_status, cog, sog, str(mmsi)))

                # Step 3: Record history (now safe from FK errors)
                cur.execute(sql_history, (str(mmsi), lat, lon, lon, lat, sog, cog, nav_status))
        except Exception as e:
            logger.error(f"Database error updating position for {mmsi}: {e}")

    def get_current_ship_total(self):
        """Returns the total number of ships currently in the database."""
        sql = "SELECT COUNT(*) as total FROM ships;"
        with self.conn.cursor() as cur:
            cur.execute(sql)
            result = cur.fetchone()
            return result['total'] if result else 0

    def get_fleet(self, region_labels=None, expiry_days=3):
        """
        Retrieves ships updated within expiry_days.
        Filters by spatial region labels if provided, else returns global.
        """
        if region_labels and len(region_labels) > 0:
            sql = """
                  SELECT DISTINCT s.* \
                  FROM ships s \
                           JOIN ship_regions r ON ST_Contains(r.boundary, s.geom)
                  WHERE r.label = ANY (%s)
                    AND s.last_position_update > NOW() - INTERVAL '%s days'
                    AND s.lat IS NOT NULL
                    AND s.lon IS NOT NULL; \
                  """
            params = (region_labels, expiry_days)
        else:
            sql = """
                  SELECT * \
                  FROM ships s
                  WHERE s.last_position_update > NOW() - INTERVAL '%s days'
                    AND s.geom IS NOT NULL
                    AND s.lat IS NOT NULL
                    AND s.lon IS NOT NULL; \
                  """
            params = (expiry_days,)

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def get_active_bboxes(self, region_labels=None):
        """
        Returns a list of [lat_s, lon_w, lat_n, lon_e] for the Harvester.
        Defaults to Global World if no regions specified.
        """
        if region_labels and len(region_labels) > 0:
            sql = """
                  SELECT ST_YMin(env), \
                         ST_XMin(env), \
                         ST_YMax(env), \
                         ST_XMax(env)
                  FROM (SELECT ST_Envelope(boundary) as env \
                        FROM ship_regions \
                        WHERE label = ANY (%s)) as sub; \
                  """
            with self.conn.cursor() as cur:
                cur.execute(sql, (region_labels,))
                rows = cur.fetchall()
                # Convert RealDictRows/Tuples to plain lists
                return [[float(r['st_ymin']), float(r['st_xmin']),
                         float(r['st_ymax']), float(r['st_xmax'])] for r in rows]

        # Fallback: Global World Bounding Box
        return [[-90.0, -180.0, 90.0, 180.0]]

    def is_in_region(self, lat, lon, region_label):
        """Quick boolean check if a point is inside a specific region."""
        sql = """
              SELECT 1 \
              FROM ship_regions
              WHERE label = %s
                AND ST_Contains(boundary, ST_SetSRID(ST_MakePoint(%s, %s), 4326)); \
              """
        with self.conn.cursor() as cur:
            cur.execute(sql, (region_label, lon, lat))
            return cur.fetchone() is not None

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

    def get_ship_track(self, mmsi, limit=100):
        """
        Retrieves historical positions for a specific ship, newest first.
        Includes a protective check to return an empty track if MMSI is missing.
        """
        if not mmsi:
            return []

        sql = """
            SELECT lat, lon FROM ship_position 
            WHERE mmsi = %s 
            ORDER BY acquired_at DESC 
            LIMIT %s;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (str(mmsi), limit))
                # Returns an empty list [] if no rows are found
                return cur.fetchall() or []
        except Exception as e:
            logger.error(f"Error fetching track for MMSI {mmsi}: {e}")
            return []

    def prune_vessel_tracks(self, expiry_days):
        """Removes position history older than the specified number of days."""
        if not expiry_days or expiry_days <= 0:
            return 0

        sql = """
              DELETE \
              FROM ship_position
              WHERE acquired_at < NOW() - INTERVAL '%s days'; \
              """
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (expiry_days,))
                deleted_rows = cur.rowcount
                if deleted_rows > 0:
                    logger.info(f"Pruned {deleted_rows} old position records.")
                return deleted_rows
        except Exception as e:
            logger.error(f"Error pruning vessel tracks: {e}")
            return 0
