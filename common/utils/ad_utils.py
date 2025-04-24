# common/utils/ad_utils.py
import logging
from typing import Dict, Any, Optional, List, Union
from common.db.database import execute_query
from common.utils.s3_utils import _upload_image_to_s3
from psycopg2.extras import RealDictCursor
from common.db.database import get_db_connection, return_connection

logger = logging.getLogger(__name__)
from common.utils.phone_parser import extract_phone_numbers_from_resource


def process_and_insert_ad(
        ad_data: Dict[str, Any],
        property_type: str,
        geo_id: int
) -> Optional[int]:
    """
    Process ad data and insert into the database, including image upload and phone extraction.
    """

    # Extract ad unique ID
    ad_unique_id = str(ad_data.get("id", ""))
    if not ad_unique_id:
        logger.warning("Missing ad ID, skipping insertion")
        return None

    # Create resource URL for the ad
    resource_url = f"https://flatfy.ua/uk/redirect/{ad_unique_id}"

    # STEP 1: Process images but don't store references yet
    uploaded_image_urls = []
    try:
        uploaded_image_urls = process_ad_images(ad_data, ad_unique_id)
        logger.info(f"Processed {len(uploaded_image_urls)} images for ad {ad_unique_id}")
    except Exception as img_upload_err:
        logger.error(f"Error uploading images for ad {ad_unique_id}: {img_upload_err}")
        # Continue anyway as we can still insert the ad

    # STEP 2: Insert the ad record and get its ID
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check if ad already exists
            check_sql = "SELECT id FROM ads WHERE external_id = %s"
            cur.execute(check_sql, [ad_unique_id])
            existing = cur.fetchone()

            if existing:
                logger.info(f"Found existing ad with external_id={ad_unique_id}, database id={existing['id']}")
                ad_id = existing['id']
            else:
                # Insert a new ad
                insert_sql = """
                INSERT INTO ads (
                    external_id, property_type, city, address, price, square_feet, 
                    rooms_count, floor, total_floors, insert_time, description, resource_url
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

                logger.info(f"Inserting new ad with external_id={ad_unique_id}")
                cur.execute(insert_sql, params)
                row = cur.fetchone()

                if not row:
                    logger.error(f"Failed to insert ad with external_id={ad_unique_id}")
                    conn.rollback()
                    return None

                ad_id = row["id"]
                logger.info(f"Successfully inserted new ad with external_id={ad_unique_id}, got database id={ad_id}")

            # At this point, we have a valid ad_id

            # STEP 3: Insert image references using the same transaction
            if uploaded_image_urls:
                logger.info(f"Inserting {len(uploaded_image_urls)} images for ad_id={ad_id}")
                for url in uploaded_image_urls:
                    img_sql = "INSERT INTO ad_images (ad_id, image_url) VALUES (%s, %s)"
                    cur.execute(img_sql, (ad_id, url))
                logger.info(f"Successfully inserted {len(uploaded_image_urls)} images for ad_id={ad_id}")

            # STEP 4: Try to extract and store phone numbers in the same transaction
            try:
                # Extract phone numbers
                logger.info(f"Extracting phones for ad_id={ad_id} from {resource_url}")
                result = extract_phone_numbers_from_resource(resource_url)
                phones = result.phone_numbers
                viber_link = result.viber_link

                # Insert phone numbers
                if phones:
                    logger.info(f"Found {len(phones)} phones for ad_id={ad_id}: {phones}")
                    for phone in phones:
                        phone_sql = "INSERT INTO ad_phones (ad_id, phone) VALUES (%s, %s)"
                        cur.execute(phone_sql, [ad_id, phone])
                        logger.info(f"Inserted phone {phone} for ad_id={ad_id}")

                # Insert viber link if available
                if viber_link:
                    viber_sql = "INSERT INTO ad_phones (ad_id, viber_link) VALUES (%s, %s)"
                    cur.execute(viber_sql, [ad_id, viber_link])
                    logger.info(f"Inserted viber link for ad_id={ad_id}")
            except Exception as e:
                logger.error(f"Error extracting/storing phones for ad_id={ad_id}: {e}")
                # Continue with the transaction - don't let phone errors stop us

            # Commit everything at once
            conn.commit()
            logger.info(f"Committed all changes for ad_id={ad_id} (external_id={ad_unique_id})")
            return ad_id
    except Exception as e:
        logger.exception(f"Error in process_and_insert_ad for external_id={ad_unique_id}: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return None
    finally:
        if conn:
            return_connection(conn)


def process_ad_images(ad_data: Dict[str, Any], ad_unique_id: str) -> List[str]:
    """
    Process and upload images associated with an ad to S3.
    """
    uploaded_image_urls = []

    try:
        images = ad_data.get('images', [])

        for image_info in images:
            image_id = image_info.get("image_id")
            if not image_id:
                continue

            original_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{image_id}.webp"
            # Updated to handle the new function signature with max_retries
            s3_url = _upload_image_to_s3(original_url, ad_unique_id, max_retries=3)

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
        # First check if the ad exists in the database
        check_sql = "SELECT id FROM ads WHERE id = %s"
        ad_exists = execute_query(check_sql, [ad_id], fetchone=True)

        if not ad_exists:
            logger.warning(f"Cannot insert images - ad_id={ad_id} does not exist in the database")
            return

        # Continue with image insertion only if the ad exists
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
