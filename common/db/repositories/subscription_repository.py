# common/db/repositories/subscription_repository.py
from typing import List, Optional, Dict, Any, Tuple, Union
import json

from sqlalchemy import and_, or_, not_
from sqlalchemy.orm import Session

from common.db.models.subscription import UserFilter
from common.db.models.user import User
from common.utils.cache import redis_cache, redis_client, CacheTTL, batch_get_cached, batch_set_cached
from common.config import GEO_ID_MAPPING, get_key_by_value


class SubscriptionRepository:
    """Repository for subscription operations"""

    @staticmethod
    @redis_cache("user_filters", ttl=CacheTTL.MEDIUM)
    def get_user_filters(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user filters with caching"""
        filters = db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
        if not filters:
            return None

        return {
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

        # Invalidate caches
        redis_client.delete(f"user_filters:{user_id}")
        matching_pattern = "matching_users:*"
        matching_keys = redis_client.keys(matching_pattern)
        if matching_keys:
            redis_client.delete(*matching_keys)

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

        # Invalidate cache
        redis_client.delete(f"user_filters:{user_id}")
        matching_pattern = "matching_users:*"
        matching_keys = redis_client.keys(matching_pattern)
        if matching_keys:
            redis_client.delete(*matching_keys)

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

        # Invalidate cache
        redis_client.delete(f"user_filters:{user_id}")
        matching_pattern = "matching_users:*"
        matching_keys = redis_client.keys(matching_pattern)
        if matching_keys:
            redis_client.delete(*matching_keys)

        return True

    @staticmethod
    def count_subscriptions(db: Session, user_id: int) -> int:
        """Count the number of subscriptions for a user"""
        return db.query(UserFilter).filter(UserFilter.user_id == user_id).count()

    @staticmethod
    def list_subscriptions_paginated(db: Session, user_id: int, page: int = 0, per_page: int = 5) -> List[
        Dict[str, Any]]:
        """Get a paginated list of subscriptions"""
        offset = page * per_page

        filters = db.query(UserFilter).filter(
            UserFilter.user_id == user_id
        ).order_by(UserFilter.id).limit(per_page).offset(offset).all()

        return [
            {
                "id": f.id,
                "user_id": f.user_id,
                "property_type": f.property_type,
                "city": f.city,
                "rooms_count": f.rooms_count,
                "price_min": f.price_min,
                "price_max": f.price_max,
                "is_paused": f.is_paused
            }
            for f in filters
        ]

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

        # Invalidate caches
        redis_client.delete(f"user_filters:{user_id}")
        redis_client.delete(f"user_subscriptions_list:{user_id}")
        matching_pattern = "matching_users:*"
        matching_keys = redis_client.keys(matching_pattern)
        if matching_keys:
            redis_client.delete(*matching_keys)

        return True