# common/db/repositories/subscription_repository.py
from datetime import datetime
from typing import List, Optional, Dict, Any

import logging
from sqlalchemy import or_
from sqlalchemy.orm import Session

from common.db.models.subscription import UserFilter
from common.db.models.user import User
from common.utils.cache import CacheTTL
from common.config import GEO_ID_MAPPING, get_key_by_value
from common.utils.cache_managers import SubscriptionCacheManager, UserCacheManager, BaseCacheManager
from common.utils.cache import get_entity_cache_key

logger = logging.getLogger(__name__)

class SubscriptionRepository:
    """Repository for subscription operations"""

    @staticmethod
    def get_user_filters(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user filters with caching"""
        # Try to get from cache first using the cache manager
        cached_filters = UserCacheManager.get_filters(user_id)
        if cached_filters:
            return cached_filters

        # Cache miss, query database
        filters = db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
        if not filters:
            return None

        # Convert to dict
        filters_dict = {
            "id": filters.id,
            "user_id": filters.user_id,
            "property_type": filters.property_type,
            "city": filters.city,
            "rooms_count": filters.rooms_count,
            "price_min": filters.price_min,
            "price_max": filters.price_max,
            "is_paused": filters.is_paused,
            "floor_max": filters.floor_max,
            "is_not_first_floor": filters.is_not_first_floor,
            "is_not_last_floor": filters.is_not_last_floor,
            "is_last_floor_only": filters.is_last_floor_only,
            "pets_allowed": filters.pets_allowed,
            "without_broker": filters.without_broker
        }

        # Cache the result
        UserCacheManager.set_filters(user_id, filters_dict)

        return filters_dict

    @staticmethod
    def update_user_filter(db: Session, user_id: int, filters_data: Dict[str, Any]) -> UserFilter:
        """Update or create user filters"""
        # Check if user exists first
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User ID {user_id} does not exist")

        # Convert city name to ID if needed
        city = filters_data.get('city')
        geo_id = get_key_by_value(city, GEO_ID_MAPPING) if city else None

        # Get existing filter or create new one
        user_filter = db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
        if not user_filter:
            user_filter = UserFilter(user_id=user_id)
            db.add(user_filter)

        # Update fields from filters_data
        user_filter.property_type = filters_data.get('property_type')
        user_filter.city = geo_id
        user_filter.rooms_count = filters_data.get('rooms')
        user_filter.price_min = filters_data.get('price_min')
        user_filter.price_max = filters_data.get('price_max')

        # Advanced filters if provided
        if 'floor_max' in filters_data:
            user_filter.floor_max = filters_data.get('floor_max')
        if 'is_not_first_floor' in filters_data:
            user_filter.is_not_first_floor = filters_data.get('is_not_first_floor')
        if 'is_not_last_floor' in filters_data:
            user_filter.is_not_last_floor = filters_data.get('is_not_last_floor')
        if 'is_last_floor_only' in filters_data:
            user_filter.is_last_floor_only = filters_data.get('is_last_floor_only')
        if 'pets_allowed' in filters_data:
            user_filter.pets_allowed = filters_data.get('pets_allowed')
        if 'without_broker' in filters_data:
            user_filter.without_broker = filters_data.get('without_broker')

        db.commit()
        db.refresh(user_filter)

        # Invalidate cache using the cache manager
        SubscriptionCacheManager.invalidate_all(user_id)
        UserCacheManager.invalidate_all(user_id)

        return user_filter

    @staticmethod
    def enable_subscription(db: Session, user_id: int) -> bool:
        """Enable subscription for a user"""
        filters = db.query(UserFilter).filter(UserFilter.user_id == user_id).all()
        if not filters:
            return False

        for f in filters:
            f.is_paused = False

        db.commit()

        # Invalidate cache using the cache manager
        SubscriptionCacheManager.invalidate_all(user_id)

        return True

    @staticmethod
    def disable_subscription(db: Session, user_id: int) -> bool:
        """Disable subscription for a user"""
        filters = db.query(UserFilter).filter(UserFilter.user_id == user_id).all()
        if not filters:
            return False

        for f in filters:
            f.is_paused = True

        db.commit()

        # Invalidate cache using the cache manager
        SubscriptionCacheManager.invalidate_all(user_id)

        return True

    @staticmethod
    def remove_subscription(db: Session, subscription_id: int, user_id: int) -> bool:
        """Remove a subscription"""
        filter_to_remove = db.query(UserFilter).filter(
            UserFilter.id == subscription_id,
            UserFilter.user_id == user_id
        ).first()

        if not filter_to_remove:
            return False

        db.delete(filter_to_remove)
        db.commit()

        # Invalidate cache using the cache manager
        SubscriptionCacheManager.invalidate_all(user_id, subscription_id)

        return True

    @staticmethod
    def count_subscriptions(db: Session, user_id: int) -> int:
        """Count the number of subscriptions for a user"""
        return db.query(UserFilter).filter(UserFilter.user_id == user_id).count()

    @staticmethod
    def list_subscriptions_paginated(db: Session, user_id: int, page: int = 0, per_page: int = 5) -> List[
        Dict[str, Any]]:
        """Get a paginated list of subscriptions with caching"""
        # Create a cache key that includes pagination parameters
        cache_key = get_entity_cache_key("user_subscriptions_paginated", user_id, f"{page}:{per_page}")

        # Try to get from the cache first
        cached_data = BaseCacheManager.get(cache_key)
        if cached_data:
            return cached_data

        # Cache miss, query database
        offset = page * per_page

        filters = db.query(UserFilter).filter(
            UserFilter.user_id == user_id
        ).order_by(UserFilter.id).limit(per_page).offset(offset).all()

        # Format the results
        result = []
        for f in filters:
            # Convert geo_id to city name if available
            city_name = GEO_ID_MAPPING.get(f.city) if f.city else None

            sub_dict = {
                "id": f.id,
                "user_id": f.user_id,
                "property_type": f.property_type,
                "city": f.city,
                "city_name": city_name,
                "rooms_count": f.rooms_count,
                "price_min": f.price_min,
                "price_max": f.price_max,
                "is_paused": f.is_paused
            }
            result.append(sub_dict)

        # Cache the result (shorter TTL for paginated data)
        BaseCacheManager.set(cache_key, result, CacheTTL.SHORT)

        return result

    @staticmethod
    def list_subscriptions(db: Session, user_id: int) -> List[Dict[str, Any]]:
        """List user subscriptions with caching"""
        # Try to get from the cache first using the cache manager
        cached_subscriptions = SubscriptionCacheManager.get_user_subscriptions(user_id)
        if cached_subscriptions:
            return cached_subscriptions

        # Cache miss, query database
        filters = db.query(UserFilter).filter(UserFilter.user_id == user_id).all()

        result = []
        for f in filters:
            # Convert geo_id to city name if available
            from common.config import GEO_ID_MAPPING
            city_name = GEO_ID_MAPPING.get(f.city) if f.city else None

            sub_dict = {
                "id": f.id,
                "property_type": f.property_type,
                "city_id": f.city,
                "city_name": city_name,
                "rooms_count": f.rooms_count,
                "price_min": f.price_min,
                "price_max": f.price_max,
                "is_paused": f.is_paused
            }
            result.append(sub_dict)

        # Cache the result
        SubscriptionCacheManager.set_user_subscriptions(user_id, result)

        return result

    @staticmethod
    def transfer_subscriptions(db: Session, from_user_id: int, to_user_id: int) -> bool:
        """Transfer subscriptions from one user to another"""
        # Get all subscriptions for the source user
        subscriptions = db.query(UserFilter).filter(UserFilter.user_id == from_user_id).all()

        if not subscriptions:
            return True  # Nothing to transfer

        # Check if target user already has any of these subscriptions
        for sub in subscriptions:
            # Check for duplicate with same parameters
            duplicate = db.query(UserFilter).filter(
                UserFilter.user_id == to_user_id,
                UserFilter.property_type == sub.property_type,
                UserFilter.city == sub.city,
                UserFilter.price_min == sub.price_min,
                UserFilter.price_max == sub.price_max
            ).first()

            if not duplicate:
                # Create a new subscription for the target user
                new_sub = UserFilter(
                    user_id=to_user_id,
                    property_type=sub.property_type,
                    city=sub.city,
                    rooms_count=sub.rooms_count,
                    price_min=sub.price_min,
                    price_max=sub.price_max,
                    is_paused=sub.is_paused,
                    floor_max=sub.floor_max,
                    is_not_first_floor=sub.is_not_first_floor,
                    is_not_last_floor=sub.is_not_last_floor,
                    is_last_floor_only=sub.is_last_floor_only,
                    pets_allowed=sub.pets_allowed,
                    without_broker=sub.without_broker
                )
                db.add(new_sub)

        # Commit changes
        db.commit()
        return True

    @staticmethod
    def add_subscription(db: Session, user_id: int, filter_data: Dict[str, Any]) -> UserFilter:
        """Add a new subscription"""
        user_filter = UserFilter(
            user_id=user_id,
            property_type=filter_data.get('property_type'),
            city=filter_data.get('city'),
            rooms_count=filter_data.get('rooms_count'),
            price_min=filter_data.get('price_min'),
            price_max=filter_data.get('price_max')
        )
        db.add(user_filter)
        db.commit()
        db.refresh(user_filter)
        return user_filter

    @staticmethod
    def enable_subscription_by_id(db: Session, subscription_id: int, user_id: int) -> bool:
        """
        Enable a specific subscription by its ID.

        Args:
            db: Database session
            subscription_id: ID of the subscription to enable
            user_id: ID of the user who owns the subscription

        Returns:
            True if successful, False if subscription not found
        """
        subscription = db.query(UserFilter).filter(
            UserFilter.id == subscription_id,
            UserFilter.user_id == user_id
        ).first()

        if not subscription:
            return False

        subscription.is_paused = False
        db.commit()
        return True


    @staticmethod
    def get_subscription_data(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
        """Get subscription data for a user"""
        user_filter = db.query(UserFilter).filter(UserFilter.user_id == user_id).first()

        if not user_filter:
            return None

        return {
            "id": user_filter.id,
            "user_id": user_filter.user_id,
            "property_type": user_filter.property_type,
            "city": user_filter.city,
            "rooms_count": user_filter.rooms_count,
            "price_min": user_filter.price_min,
            "price_max": user_filter.price_max,
            "is_paused": user_filter.is_paused,
            # Add other fields as needed
        }

    @staticmethod
    def get_active_cities(db: Session) -> List[int]:
        """
        Get all distinct cities from active users' filters.

        Args:
            db: Database session

        Returns:
            List of distinct city IDs that have active subscriptions
        """
        try:
            cities = db.query(UserFilter.city) \
                .join(User, UserFilter.user_id == User.id) \
                .filter(
                UserFilter.city.isnot(None),
                UserFilter.is_paused == False,
                or_(
                    User.subscription_until > datetime.now(),
                    User.free_until > datetime.now()
                )
            ) \
                .distinct() \
                .all()

            # Extract city IDs from result tuples
            return [city[0] for city in cities]
        except Exception as e:
            logger.error(f"Error getting active cities: {e}")
            return []