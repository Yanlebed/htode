# common/db/repositories/ad_repository.py
from typing import List, Optional, Dict, Any, Union
import decimal
import json
from datetime import datetime

from sqlalchemy import and_, or_, not_
from sqlalchemy.orm import Session, joinedload

from common.db.models.ad import Ad, AdImage, AdPhone
from common.utils.cache import redis_cache, redis_client, CacheTTL


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