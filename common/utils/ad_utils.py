# common/utils/ad_utils.py

import logging
from typing import Dict, Any, Optional, List, Union
from common.db.session import db_session
from common.db.repositories.ad_repository import AdRepository
from common.utils.s3_utils import _upload_image_to_s3
from common.utils.phone_parser import extract_phone_numbers_from_resource
from common.db.models.ad import Ad

logger = logging.getLogger(__name__)


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
    try:
        with db_session() as db:
            # Check if ad already exists
            existing_ad = AdRepository.get_by_external_id(db, ad_unique_id)

            if existing_ad:
                logger.info(f"Found existing ad with external_id={ad_unique_id}, database id={existing_ad.id}")
                ad_id = existing_ad.id
            else:
                # Create new ad data dictionary
                new_ad_data = {
                    "external_id": ad_unique_id,
                    "property_type": property_type,
                    "city": geo_id,
                    "address": ad_data.get("header"),
                    "price": ad_data.get("price"),
                    "square_feet": ad_data.get("area_total"),
                    "rooms_count": ad_data.get("room_count"),
                    "floor": ad_data.get("floor"),
                    "total_floors": ad_data.get("floor_count"),
                    "insert_time": ad_data.get("insert_time"),
                    "description": ad_data.get("text"),
                    "resource_url": resource_url
                }

                # Insert new ad
                ad = AdRepository.create_ad(db, new_ad_data)
                ad_id = ad.id
                logger.info(f"Successfully inserted new ad with external_id={ad_unique_id}, got database id={ad_id}")

            # At this point, we have a valid ad_id

            # STEP 3: Insert image references
            if uploaded_image_urls:
                logger.info(f"Inserting {len(uploaded_image_urls)} images for ad_id={ad_id}")
                for url in uploaded_image_urls:
                    AdRepository.add_image(db, ad_id, url)

                logger.info(f"Successfully inserted {len(uploaded_image_urls)} images for ad_id={ad_id}")

            # STEP 4: Try to extract and store phone numbers
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
                        AdRepository.add_phone(db, ad_id, phone)
                        logger.info(f"Inserted phone {phone} for ad_id={ad_id}")

                # Insert viber link if available
                if viber_link:
                    AdRepository.add_phone(db, ad_id, None, viber_link)
                    logger.info(f"Inserted viber link for ad_id={ad_id}")
            except Exception as e:
                logger.error(f"Error extracting/storing phones for ad_id={ad_id}: {e}")
                # Continue - don't let phone errors stop us

            db.commit()
            logger.info(f"Committed all changes for ad_id={ad_id} (external_id={ad_unique_id})")
            return ad_id
    except Exception as e:
        logger.exception(f"Error in process_and_insert_ad for external_id={ad_unique_id}: {e}")
        return None


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
        with db_session() as db:
            # Check if the ad exists
            ad = db.query(Ad).get(ad_id)

            if not ad:
                logger.warning(f"Cannot insert images - ad_id={ad_id} does not exist in the database")
                return

            # Insert images
            for url in image_urls:
                AdRepository.add_image(db, ad_id, url)

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

        with db_session() as db:
            image_urls = AdRepository.get_ad_images(db, ad_id)
            return image_urls

    except Exception as e:
        logger.exception(f"Error getting ad images: {e}")
        return []