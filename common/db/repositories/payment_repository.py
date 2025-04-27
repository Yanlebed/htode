# common/db/repositories/payment_repository.py

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import desc
from sqlalchemy.orm import Session
from common.db.models.payment import PaymentOrder, PaymentHistory
from common.db.repositories.base_repository import BaseRepository


class PaymentRepository(BaseRepository):
    """Repository for payment operations"""

    @staticmethod
    def get_order_by_id(db: Session, order_id: str) -> Optional[PaymentOrder]:
        """Get payment order by ID"""
        return db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()

    @staticmethod
    def create_order(db: Session, user_id: int, order_id: str, amount: float, period: str) -> PaymentOrder:
        """Create a new payment order"""
        order = PaymentOrder(
            user_id=user_id,
            order_id=order_id,
            amount=amount,
            period=period,
            status="pending"
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def update_order_status(db: Session, order_id: str, status: str) -> Optional[PaymentOrder]:
        """Update payment order status"""
        order = db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()
        if order:
            order.status = status
            order.updated_at = datetime.now()
            db.commit()
            db.refresh(order)
        return order

    @staticmethod
    def create_payment_history(db: Session, payment_data: Dict[str, Any]) -> PaymentHistory:
        """Create payment history record"""
        payment_history = PaymentHistory(**payment_data)
        db.add(payment_history)
        db.commit()
        db.refresh(payment_history)
        return payment_history

    @staticmethod
    def get_user_payment_history(db: Session, user_id: int, limit: int = 10) -> List[PaymentHistory]:
        """Get payment history for user"""
        return db.query(PaymentHistory).filter(
            PaymentHistory.user_id == user_id
        ).order_by(desc(PaymentHistory.created_at)).limit(limit).all()

    @staticmethod
    def get_active_orders(db: Session, user_id: int) -> List[PaymentOrder]:
        """Get active (pending) orders for user"""
        return db.query(PaymentOrder).filter(
            PaymentOrder.user_id == user_id,
            PaymentOrder.status == "pending"
        ).all()

    @staticmethod
    def cancel_expired_orders(db: Session, hours: int = 24) -> int:
        """Cancel orders that have been pending for more than specified hours"""
        expiry_time = datetime.now() - timedelta(hours=hours)

        expired_orders = db.query(PaymentOrder).filter(
            PaymentOrder.status == "pending",
            PaymentOrder.created_at < expiry_time
        ).all()

        for order in expired_orders:
            order.status = "cancelled"
            order.updated_at = datetime.now()

        db.commit()
        return len(expired_orders)