import os
import io
import requests
import logging
from PIL import Image

logger = logging.getLogger(__name__)


class NASAGIBSDownloader:
    def __init__(self):
        self.base_url = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"

    def download_region_map(self, bbox, target_width, target_height, outfile, is_night=False):
        """
        Downloads a regional map. Clamps to 180 longitude to prevent Xplanet rendering artifacts.
        Returns: (success_bool, final_bbox)
        """
        lon_min, lat_min, lon_max, lat_max = bbox

        # 1. Clamp to Dateline and adjust width to maintain aspect ratio
        if lon_max > 180.0:
            logger.info(f"Clamping {outfile} to 180 longitude to prevent rendering gaps.")

            original_span = lon_max - lon_min
            clamped_span = 180.0 - lon_min

            # Reduce width proportionally so the land isn't stretched
            target_width = int(target_width * (clamped_span / original_span))
            lon_max = 180.0

        final_bbox = [lon_min, lat_min, lon_max, lat_max]

        # 2. Fetch the single tile (no stitching required)
        img = self._fetch_wms_image(final_bbox, is_night, width=target_width, height=target_height)

        if img:
            os.makedirs(os.path.dirname(outfile), exist_ok=True)
            img.save(outfile, "JPEG", quality=90)
            return True, final_bbox

        return False, bbox

    def _fetch_wms_image(self, bbox, is_night, width, height):
        layer = "VIIRS_Black_Marble" if is_night else "BlueMarble_ShadedRelief_Bathymetry"
        bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"

        params = {
            "service": "WMS",
            "request": "GetMap",
            "version": "1.1.1",
            "layers": layer,
            "styles": "",
            "format": "image/jpeg",
            "transparent": "false",
            "srs": "EPSG:4326",
            "width": str(width),
            "height": str(height),
            "bbox": bbox_str
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content))
        except Exception as e:
            logger.error(f"NASA WMS Fetch Error: {e}")
            return None
