# common/db/repositories/favorite_repository.py
from typing import List, Dict, Any, Optional
import decimal

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import func

from common.db.models.favorite import FavoriteAd
from common.db.models.ad import Ad
from common.utils.cache import redis_cache, redis_client, CacheTTL


class FavoriteRepository:
    """Repository for favorite ad operations"""

    @staticmethod
    def add_favorite(db: Session, user_id: int, ad_id: int) -> Optional[FavoriteAd]:
        """Add a favorite ad"""
        # Check limit of 50 favorites
        favorites_count = db.query(func.count(FavoriteAd.id)).filter(
            FavoriteAd.user_id == user_id
        ).scalar()

        if favorites_count >= 50:
            raise ValueError("You already have 50 favorite ads, cannot add more.")

        # Check if already exists
        existing = db.query(FavoriteAd).filter(
            FavoriteAd.user_id == user_id,
            FavoriteAd.ad_id == ad_id
        ).first()

        if existing:
            return existing

        # Create new favorite
        favorite = FavoriteAd(user_id=user_id, ad_id=ad_id)
        db.add(favorite)
        db.commit()
        db.refresh(favorite)

        # Invalidate cache
        redis_client.delete(f"user_favorites:{user_id}")

        return favorite

    @staticmethod
    def remove_favorite(db: Session, user_id: int, ad_id: int) -> bool:
        """Remove a favorite ad"""
        favorite = db.query(FavoriteAd).filter(
            FavoriteAd.user_id == user_id,
            FavoriteAd.ad_id == ad_id
        ).first()

        if not favorite:
            return False

        db.delete(favorite)
        db.commit()

        # Invalidate cache
        redis_client.delete(f"user_favorites:{user_id}")

        return True

    @staticmethod
    @redis_cache("user_favorites", ttl=CacheTTL.MEDIUM)
    def list_favorites(db: Session, user_id: int) -> List[Dict[str, Any]]:
        """List user's favorite ads with eager loading"""
        favorites = db.query(FavoriteAd) \
            .filter(FavoriteAd.user_id == user_id) \
            .options(
            joinedload(FavoriteAd.ad).joinedload(Ad.images),
            joinedload(FavoriteAd.ad).joinedload(Ad.phones)
        ) \
            .order_by(FavoriteAd.created_at.desc()) \
            .all()

        result = []
        for fav in favorites:
            ad = fav.ad
            ad_dict = {
                "favorite_id": fav.id,
                "ad_id": ad.id,
                "price": float(ad.price) if isinstance(ad.price, decimal.Decimal) else ad.price,
                "address": ad.address,
                "city": ad.city,
                "property_type": ad.property_type,
                "rooms_count": ad.rooms_count,
                "resource_url": ad.resource_url,
                "external_id": ad.external_id,
                "square_feet": float(ad.square_feet) if isinstance(ad.square_feet, decimal.Decimal) else ad.square_feet,
                "floor": ad.floor,
                "total_floors": ad.total_floors,
                "images": [img.image_url for img in ad.images],
                "phones": [phone.phone for phone in ad.phones if phone.phone],
                "viber_link": next((phone.viber_link for phone in ad.phones if phone.viber_link), None)
            }
            result.append(ad_dict)

        return result