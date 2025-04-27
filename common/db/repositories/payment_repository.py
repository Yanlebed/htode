# common/db/repositories/payment_repository.py
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from common.db.models.payment import PaymentOrder, PaymentHistory


class PaymentRepository:
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