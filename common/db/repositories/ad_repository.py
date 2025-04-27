# common/db/repositories/ad_repository.py (Updated)
from typing import List, Optional, Dict, Any, Union
import decimal
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, not_, text
from sqlalchemy.orm import Session, joinedload

from common.db.models import FavoriteAd
from common.db.models.ad import Ad, AdImage, AdPhone
from common.utils.cache import redis_cache, redis_client, CacheTTL
from common.config import GEO_ID_MAPPING, get_key_by_value

logger = logging.getLogger(__name__)


class AdRepository:
    """Repository for ad operations"""

    @staticmethod
    def get_by_id(db: Session, ad_id: int) -> Optional[Ad]:
        """Get ad by database ID"""
        return db.query(Ad).filter(Ad.id == ad_id).first()

    @staticmethod
    def get_by_external_id(db: Session, external_id: str) -> Optional[Ad]:
        """Get ad by external ID"""
        return db.query(Ad).filter(Ad.external_id == external_id).first()

    @staticmethod
    def get_by_resource_url(db: Session, resource_url: str) -> Optional[Ad]:
        """Get ad by resource URL"""
        return db.query(Ad).filter(Ad.resource_url == resource_url).first()

    @staticmethod
    @redis_cache("full_ad", ttl=CacheTTL.MEDIUM)
    def get_full_ad_data(db: Session, ad_id: int) -> Optional[Dict[str, Any]]:
        """Get complete ad data with images and phones"""
        ad = db.query(Ad) \
            .options(
            joinedload(Ad.images),
            joinedload(Ad.phones)
        ) \
            .filter(Ad.id == ad_id) \
            .first()

        if not ad:
            return None

        # Convert to dict
        ad_dict = {
            "id": ad.id,
            "external_id": ad.external_id,
            "property_type": ad.property_type,
            "city": ad.city,
            "address": ad.address,
            "price": float(ad.price) if isinstance(ad.price, decimal.Decimal) else ad.price,
            "square_feet": float(ad.square_feet) if isinstance(ad.square_feet, decimal.Decimal) else ad.square_feet,
            "rooms_count": ad.rooms_count,
            "floor": ad.floor,
            "total_floors": ad.total_floors,
            "insert_time": ad.insert_time.isoformat() if ad.insert_time else None,
            "description": ad.description,
            "resource_url": ad.resource_url,
            "images": [img.image_url for img in ad.images],
            "phones": [phone.phone for phone in ad.phones if phone.phone],
            "viber_link": next((phone.viber_link for phone in ad.phones if phone.viber_link), None)
        }

        return ad_dict

    @staticmethod
    def create_ad(db: Session, ad_data: Dict[str, Any]) -> Ad:
        """Create a new ad"""
        ad = Ad(
            external_id=ad_data.get("external_id"),
            property_type=ad_data.get("property_type"),
            city=ad_data.get("city"),
            address=ad_data.get("address"),
            price=ad_data.get("price"),
            square_feet=ad_data.get("square_feet"),
            rooms_count=ad_data.get("rooms_count"),
            floor=ad_data.get("floor"),
            total_floors=ad_data.get("total_floors"),
            description=ad_data.get("description"),
            resource_url=ad_data.get("resource_url"),
            insert_time=ad_data.get("insert_time") or datetime.now()
        )
        db.add(ad)
        db.commit()
        db.refresh(ad)
        return ad

    @staticmethod
    def add_image(db: Session, ad_id: int, image_url: str) -> AdImage:
        """Add an image to an ad"""
        image = AdImage(ad_id=ad_id, image_url=image_url)
        db.add(image)
        db.commit()
        db.refresh(image)

        # Invalidate cache
        redis_client.delete(f"full_ad:{ad_id}")
        redis_client.delete(f"ad_images:{ad_id}")

        return image

    @staticmethod
    def add_phone(db: Session, ad_id: int, phone: str, viber_link: Optional[str] = None) -> AdPhone:
        """Add a phone to an ad"""
        ad_phone = AdPhone(ad_id=ad_id, phone=phone, viber_link=viber_link)
        db.add(ad_phone)
        db.commit()
        db.refresh(ad_phone)

        # Invalidate cache
        redis_client.delete(f"full_ad:{ad_id}")

        return ad_phone

    @staticmethod
    @redis_cache("ad_images", ttl=CacheTTL.LONG)
    def get_ad_images(db: Session, ad_id: int) -> List[str]:
        """Get all images for an ad"""
        images = db.query(AdImage).filter(AdImage.ad_id == ad_id).all()
        return [img.image_url for img in images]

    @staticmethod
    @redis_cache("ad_description", ttl=CacheTTL.LONG)
    def get_full_description(db: Session, resource_url: str) -> Optional[str]:
        """Get full ad description by resource URL"""
        ad = db.query(Ad).filter(Ad.resource_url == resource_url).first()
        return ad.description if ad else None

    @staticmethod
    @redis_cache("ads_period", ttl=300)  # 5 minute cache
    def fetch_ads_for_period(db: Session, filters: Dict[str, Any], days: int, limit: int = 3) -> List[Ad]:
        """
        Query ads table, matching the user's filters,
        for ads from the last `days` days. Return up to `limit` ads.

        Args:
            db: Database session
            filters: Dictionary of filter criteria
            days: Number of days to look back
            limit: Maximum number of ads to return

        Returns:
            List of matching Ad objects
        """
        query = db.query(Ad)

        # Apply filters
        city = filters.get('city')
        if city:
            geo_id = get_key_by_value(city, GEO_ID_MAPPING)
            if geo_id:
                query = query.filter(Ad.city == geo_id)

        if filters.get('property_type'):
            query = query.filter(Ad.property_type == filters['property_type'])

        if filters.get('rooms') is not None:
            # Handle array membership
            rooms = filters['rooms']
            if rooms:
                # Using IN to match any of the room values
                query = query.filter(Ad.rooms_count.in_(rooms))

        if filters.get('price_min') is not None:
            query = query.filter(Ad.price >= filters['price_min'])

        if filters.get('price_max') is not None:
            query = query.filter(Ad.price <= filters['price_max'])

        # Filter by date
        days_ago = datetime.now() - timedelta(days=days)
        query = query.filter(Ad.insert_time >= days_ago)

        # Order by newest first
        query = query.order_by(Ad.insert_time.desc())

        # Limit results
        query = query.limit(limit)

        return query.all()

    @staticmethod
    def find_users_for_ad(db: Session, ad) -> List[int]:
        """
        Finds users whose subscription filters match this ad.

        Args:
            db: Database session
            ad: Ad object or dictionary

        Returns:
            List of user IDs
        """
        from common.db.models.user import User
        from common.db.models.subscription import UserFilter

        try:
            # Create a cache key based on the ad's primary attributes that affect matching
            ad_id = ad.id if hasattr(ad, 'id') else ad.get('id')
            cache_key = f"matching_users:{ad_id}"

            # Try to get results from cache first
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)

            # Get ad properties for matching
            if hasattr(ad, 'property_type'):
                # It's an ORM object
                ad_property_type = ad.property_type
                ad_city = ad.city
                ad_rooms = ad.rooms_count
                ad_price = ad.price
            else:
                # It's a dictionary
                ad_property_type = ad.get('property_type')
                ad_city = ad.get('city')
                ad_rooms = ad.get('rooms_count')
                ad_price = ad.get('price')

            # Query users with matching filters
            query = db.query(User.id).join(UserFilter, User.id == UserFilter.user_id)

            # Filter for active users only
            query = query.filter(or_(
                User.free_until > datetime.now(),
                User.subscription_until > datetime.now()
            ))

            # Filter for non-paused subscriptions
            query = query.filter(UserFilter.is_paused == False)

            # Apply ad property filters
            filters = []

            # Property type filter (if set)
            filters.append(or_(
                UserFilter.property_type == None,
                UserFilter.property_type == ad_property_type
            ))

            # City filter (if set)
            filters.append(or_(
                UserFilter.city == None,
                UserFilter.city == ad_city
            ))

            # Rooms filter (array membership)
            filters.append(or_(
                UserFilter.rooms_count == None,
                UserFilter.rooms_count.any(ad_rooms)
            ))

            # Price range filter
            filters.append(or_(
                UserFilter.price_min == None,
                ad_price >= UserFilter.price_min
            ))

            filters.append(or_(
                UserFilter.price_max == None,
                ad_price <= UserFilter.price_max
            ))

            # Apply all filters
            query = query.filter(and_(*filters))

            # Execute query
            results = query.all()
            user_ids = [result[0] for result in results]

            # Cache the results for 1 hour
            redis_client.set(cache_key, json.dumps(user_ids), ex=CacheTTL.STANDARD)

            return user_ids

        except Exception as e:
            logger.error(f"Error finding users for ad {ad_id if 'ad_id' in locals() else 'unknown'}: {e}")
            return []

    @staticmethod
    def delete_with_related(db: Session, ad_id: int) -> bool:
        """
        Delete an ad and all its related data (images, phones, favorites) using transaction.

        Args:
            db: Database session
            ad_id: ID of the ad to delete

        Returns:
            True if the ad was deleted successfully, False otherwise
        """
        try:
            # Get the ad first
            ad = db.query(Ad).get(ad_id)
            if not ad:
                logger.warning(f"Attempted to delete non-existent ad with ID {ad_id}")
                return False

            # Delete related data
            # Note: You can also rely on CASCADE if set up in your model relationships

            # Delete from favorite_ads
            db.query(FavoriteAd).filter(FavoriteAd.ad_id == ad_id).delete()

            # Delete from ad_phones
            db.query(AdPhone).filter(AdPhone.ad_id == ad_id).delete()

            # Delete from ad_images
            db.query(AdImage).filter(AdImage.ad_id == ad_id).delete()

            # Delete the ad itself
            db.delete(ad)
            db.commit()

            logger.info(f"Successfully deleted ad {ad_id} and related data")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting ad {ad_id}: {e}")
            return False

    @staticmethod
    def get_older_than(db: Session, cutoff_date: datetime) -> List[Ad]:
        """
        Get ads older than the specified date.

        Args:
            db: Database session
            cutoff_date: Date before which ads are considered old

        Returns:
            List of Ad objects
        """
        return db.query(Ad).filter(Ad.insert_time < cutoff_date).all()

    @staticmethod
    def get_ad_images(db: Session, ad_id: int) -> List[str]:
        """
        Get all image URLs for an ad.

        Args:
            db: Database session
            ad_id: ID of the ad

        Returns:
            List of image URLs
        """
        images = db.query(AdImage).filter(AdImage.ad_id == ad_id).all()
        return [img.image_url for img in images]
