# common/services/ad_service.py

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from common.db.repositories.ad_repository import AdRepository
from common.utils.unified_request_utils import make_request
from common.utils.cache_managers import AdCacheManager

logger = logging.getLogger(__name__)


class AdService:
    @staticmethod
    def get_full_ad_data(db: Session, ad_id: int) -> Optional[Dict[str, Any]]:
        """
        Get complete ad data with related entities.

        Args:
            db: Database session
            ad_id: ID of the ad

        Returns:
            Dictionary with ad data or None if not found
        """
        # Try to get from the cache first using the cache manager
        cached_data = AdCacheManager.get_full_ad_data(ad_id)
        if cached_data:
            return cached_data

        # Get from a repository
        ad_data = AdRepository.get_full_ad_data(db, ad_id)

        # Cache if found
        if ad_data:
            AdCacheManager.set_full_ad_data(ad_id, ad_data)

        return ad_data

    @staticmethod
    def process_and_insert_ad(
            db: Session,
            ad_data: Dict[str, Any],
            property_type: str,
            geo_id: int
    ) -> Optional[int]:
        """
        Process and insert an ad with its related data.

        Args:
            db: Database session
            ad_data: Dictionary with ad data
            property_type: Type of property
            geo_id: City geo ID

        Returns:
            ID of the created ad or None if failed
        """
        # Extract ad unique ID
        ad_unique_id = str(ad_data.get("id", ""))
        if not ad_unique_id:
            logger.warning("Missing ad ID, skipping insertion")
            return None

        # Create resource URL
        resource_url = f"https://flatfy.ua/uk/redirect/{ad_unique_id}"

        try:
            # Check if ad already exists
            existing_ad = AdRepository.get_by_external_id(db, ad_unique_id)

            if existing_ad:
                logger.info(f"Found existing ad with external_id={ad_unique_id}, database id={existing_ad.id}")
                return existing_ad.id

            # Create new ad data
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

            # Create the ad
            ad = AdRepository.create_ad(db, new_ad_data)
            ad_id = ad.id

            # Process images
            from common.utils.ad_utils import process_ad_images
            uploaded_image_urls = process_ad_images(ad_data, ad_unique_id)

            # Insert image references
            if uploaded_image_urls:
                for url in uploaded_image_urls:
                    AdRepository.add_image(db, ad_id, url)

            # Extract and store phone numbers
            from common.utils.phone_parser import extract_phone_numbers_from_resource
            result = extract_phone_numbers_from_resource(resource_url)
            phones = result.phone_numbers
            viber_link = result.viber_link

            if phones:
                for phone in phones:
                    AdRepository.add_phone(db, ad_id, phone)

            if viber_link:
                AdRepository.add_phone(db, ad_id, None, viber_link)

            db.commit()
            return ad_id

        except Exception as e:
            db.rollback()
            logger.exception(f"Error processing ad {ad_unique_id}: {e}")
            return None

    @staticmethod
    def is_ad_inactive(resource_url: str) -> bool:
        """
        Check if an ad is inactive (returns 404 or error).

        Args:
            resource_url: URL of the ad

        Returns:
            True if inactive, False if active
        """
        try:
            # Use a HEAD request to minimize data transfer
            response = make_request(
                url=resource_url,
                method='head',
                timeout=10,
                retries=2,
                raise_for_status=False
            )

            # Consider non-existent or error responses as inactive
            if not response or response.status_code >= 400:
                return True

            return False
        except Exception as e:
            logger.warning(f"Error checking ad activity for {resource_url}: {e}")
            # Consider ads with connection errors as inactive
            return True

    @staticmethod
    def cleanup_old_ads(db: Session, days_old: int = 30, check_activity: bool = True) -> Tuple[int, int]:
        """
        Clean up ads older than the specified days.

        Args:
            db: Database session
            days_old: Age threshold in days
            check_activity: Whether to check if ad is still active

        Returns:
            Tuple of (ads_deleted, images_deleted)
        """
        deleted_count = 0
        images_deleted_count = 0

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=days_old)

        # Get old ads
        old_ads = AdRepository.get_older_than(db, cutoff_date)

        for ad in old_ads:
            should_delete = True

            # Check if the ad is still active
            if check_activity and not AdService.is_ad_inactive(ad.resource_url):
                should_delete = False

            if should_delete:
                # Get images before deleting
                images = AdRepository.get_ad_images(db, ad.id)

                # Delete the ad
                if AdRepository.delete_with_related(db, ad.id):
                    deleted_count += 1

                    # Delete images from S3
                    from common.utils.s3_utils import delete_s3_image
                    for image_url in images:
                        if delete_s3_image(image_url):
                            images_deleted_count += 1

                    # Clear cache using the cache manager
                    AdCacheManager.invalidate_all(ad.id, ad.resource_url)

        return deleted_count, images_deleted_count

    @staticmethod
    def clear_ad_cache(ad_id: int, resource_url: str = None):
        """
        Clear all cache related to an ad.

        Args:
            ad_id: ID of the ad
            resource_url: Optional resource URL
        """
        # Use the cache manager to invalidate all ad-related caches
        AdCacheManager.invalidate_all(ad_id, resource_url)