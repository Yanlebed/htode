# common/utils/ad_utils.py
import logging
from typing import Dict, Any, Optional, List, Union
from common.db.database import execute_query
from common.utils.s3_utils import _upload_image_to_s3
from common.db.models import store_ad_phones

logger = logging.getLogger(__name__)


def process_and_insert_ad(
        ad_data: Dict[str, Any],
        property_type: str,
        geo_id: int
) -> Optional[int]:
    """
    Process ad data and insert into the database, including image upload and phone extraction.

    Args:
        ad_data: Dictionary containing the ad information
        property_type: Type of property (apartment, house, etc.)
        geo_id: Geographic ID of the city

    Returns:
        int: The internal database ID of the inserted ad, or None if insertion failed
    """
    try:
        # Extract ad unique ID
        ad_unique_id = str(ad_data.get("id", ""))
        if not ad_unique_id:
            logger.warning("Missing ad ID, skipping insertion")
            return None

        # Create resource URL for the ad
        resource_url = f"https://flatfy.ua/uk/redirect/{ad_unique_id}"

        # Process images by uploading them to S3
        uploaded_image_urls = process_ad_images(ad_data, ad_unique_id)

        # Prepare database insert parameters
        insert_sql = """
        INSERT INTO ads (
            external_id, property_type, city, address, price, square_feet, 
            rooms_count, floor, total_floors, insert_time, description, resource_url
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (external_id) DO UPDATE
          SET property_type = EXCLUDED.property_type,
              city = EXCLUDED.city,
              address = EXCLUDED.address,
              price = EXCLUDED.price,
              square_feet = EXCLUDED.square_feet,
              rooms_count = EXCLUDED.rooms_count,
              floor = EXCLUDED.floor,
              total_floors = EXCLUDED.total_floors,
              insert_time = EXCLUDED.insert_time,
              description = EXCLUDED.description,
              resource_url = EXCLUDED.resource_url
        RETURNING id;
        """

        params = [
            ad_unique_id,
            property_type,
            geo_id,
            ad_data.get("header"),
            ad_data.get("price"),
            ad_data.get("area_total"),
            ad_data.get("room_count"),
            ad_data.get("floor"),
            ad_data.get("floor_count"),
            ad_data.get("insert_time"),
            ad_data.get("text"),
            resource_url
        ]

        logger.info(f"Inserting ad with ID {ad_unique_id} into database")
        row = execute_query(insert_sql, params, fetchone=True)

        if not row:
            logger.error(f"Failed to insert ad with ID {ad_unique_id}")
            return None

        ad_id = row["id"]

        # Store phone numbers for the ad
        store_ad_phones(resource_url, ad_id)

        # Store images in the database
        insert_ad_images(ad_id, uploaded_image_urls)

        return ad_id

    except Exception as e:
        logger.exception(f"Error processing and inserting ad: {e}")
        return None


def process_ad_images(ad_data: Dict[str, Any], ad_unique_id: str) -> List[str]:
    """
    Process and upload images associated with an ad to S3.

    Args:
        ad_data: Ad data dictionary containing images info
        ad_unique_id: Unique ID of the ad

    Returns:
        List of uploaded S3/CloudFront URLs
    """
    uploaded_image_urls = []

    try:
        images = ad_data.get('images', [])

        for image_info in images:
            image_id = image_info.get("image_id")
            if not image_id:
                continue

            original_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{image_id}.webp"
            s3_url = _upload_image_to_s3(original_url, ad_unique_id)

            if s3_url:
                uploaded_image_urls.append(s3_url)

        logger.info(f"Processed {len(uploaded_image_urls)} images for ad {ad_unique_id}")
        return uploaded_image_urls

    except Exception as e:
        logger.exception(f"Error processing ad images: {e}")
        return uploaded_image_urls


def insert_ad_images(ad_id: int, image_urls: List[str]) -> None:
    """
    Insert ad images into the database.

    Args:
        ad_id: Database ID of the ad
        image_urls: List of S3/CloudFront URLs to insert
    """
    if not image_urls:
        return

    try:
        sql = "INSERT INTO ad_images (ad_id, image_url) VALUES (%s, %s)"
        for url in image_urls:
            execute_query(sql, (ad_id, url))
        logger.info(f"Inserted {len(image_urls)} images for ad ID {ad_id}")
    except Exception as e:
        logger.exception(f"Error inserting ad images: {e}")


def get_ad_images(ad_id: Union[int, Dict[str, Any]]) -> List[str]:
    """
    Get all images associated with an ad.

    Args:
        ad_id: Either the database ID of the ad or the ad dictionary with an 'id' key

    Returns:
        List of image URLs
    """
    try:
        # Handle either an ad dict or direct ad_id
        if isinstance(ad_id, dict):
            ad_id = ad_id.get('id')

        if not ad_id:
            return []

        sql_check = "SELECT image_url FROM ad_images WHERE ad_id = %s"
        rows = execute_query(sql_check, [ad_id], fetch=True)

        if rows:
            return [row["image_url"] for row in rows]
        return []

    except Exception as e:
        logger.exception(f"Error getting ad images: {e}")
        return []