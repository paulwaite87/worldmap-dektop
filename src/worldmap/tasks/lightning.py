import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from .common import Updater, get_bbox_center

logger = logging.getLogger(__name__)


class LightningUpdater(Updater):
    def __init__(self, config, map_data):
        super().__init__(config, "Lightning", map_data)
        self.set_output_path()

    def get_grid_points(self):
        """Generates (lat, lon) points to cover the bbox."""
        lon_min, lat_min, lon_max, lat_max = self.map_region_bbox
        step = 0.45

        points = []
        curr_lat = lat_min + (step / 2)
        while curr_lat <= lat_max:
            curr_lon = lon_min + (step / 2)
            while curr_lon <= lon_max:
                points.append((curr_lat, curr_lon))
                curr_lon += step
            curr_lat += step
        return points

    async def fetch_block(self, session, lat, lon, start_date, end_date, api_key):
        """Fetches a single 50km block."""
        base_url = self.settings.get("url")
        params = {
            "lat": f"{lat:.4f}",
            "lon": f"{lon:.4f}",
            "radius": 50,
            "start_date": start_date,
            "end_date": end_date,
            "apikey": api_key
        }

        try:
            # Short timeout per block to prevent hanging
            async with session.get(base_url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("lightnings", [])
                return []
        except Exception:
            return []

    async def run(self):
        self.config.load()
        self.exit_if_disabled()

        api_key = self.settings.get("api_key")
        if not api_key:
            return

        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(minutes=60)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end_date = now.strftime('%Y-%m-%dT%H:%M:%SZ')

        grid_points = self.get_grid_points()
        all_strikes = {}

        # Batch settings: 5 concurrent requests at a time
        batch_size = 5

        # Explicitly configure the connector for stability
        connector = aiohttp.TCPConnector(limit_per_host=batch_size, force_close=True)

        async with aiohttp.ClientSession(connector=connector) as session:
            # Process grid points in chunks to avoid hanging
            for i in range(0, len(grid_points), batch_size):
                batch = grid_points[i: i + batch_size]
                logger.debug(f"Processing lightning batch {i // batch_size + 1}...")

                tasks = [
                    self.fetch_block(session, p[0], p[1], start_date, end_date, api_key)
                    for p in batch
                ]

                results = await asyncio.gather(*tasks)

                for strike_list in results:
                    for s in strike_list:
                        all_strikes[s['id']] = s

                # Tiny breather to let the network stack clear
                await asyncio.sleep(0.1)

        if not all_strikes:
            logger.info(f"Scan complete: No strikes found in {len(grid_points)} blocks.")
            return

        written_count = 0
        current_time = datetime.now(timezone.utc)

        with open(self.output_path, "w") as f:
            for s in all_strikes.values():
                try:
                    s_lat, s_lon = float(s['lat']), float(s['lon'])
                    if not self.map_data.region.is_in_region(s_lat, s_lon):
                        continue

                    dt_str = s['datetime'].replace("+00:00", "Z")
                    ts = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    age_mins = (current_time - ts).total_seconds() / 60

                    icon = "bolt_red.png"
                    if age_mins < 5:
                        icon = "bolt_white.png"
                    elif age_mins < 20:
                        icon = "bolt_yellow.png"
                    elif age_mins > 60:
                        continue

                    f.write(f'{s_lat} {s_lon} image={icon}\n')
                    written_count += 1
                except Exception:
                    continue

        logger.info(f"Lightning update complete. Found {written_count} strikes across {len(grid_points)} blocks.")