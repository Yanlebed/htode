# common/db/repositories/payment_repository.py

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import desc
from sqlalchemy.orm import Session

from common.db.models.payment import PaymentOrder, PaymentHistory
from common.db.repositories.base_repository import BaseRepository
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the repository logger
from . import logger


class PaymentRepository(BaseRepository):
    """Repository for payment operations"""

    @staticmethod
    @log_operation("get_order_by_id")
    def get_order_by_id(db: Session, order_id: str) -> Optional[PaymentOrder]:
        """Get payment order by ID"""
        with log_context(logger, order_id=order_id):
            order = db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()

            if order:
                logger.debug("Found payment order", extra={
                    'order_id': order_id,
                    'user_id': order.user_id,
                    'status': order.status
                })
            else:
                logger.debug("Payment order not found", extra={'order_id': order_id})

            return order

    @staticmethod
    @log_operation("create_order")
    def create_order(db: Session, user_id: int, order_id: str, amount: float, period: str) -> PaymentOrder:
        """Create a new payment order"""
        with log_context(logger, user_id=user_id, order_id=order_id, amount=amount, period=period):
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

            logger.info("Created payment order", extra={
                'id': order.id,
                'order_id': order_id,
                'user_id': user_id,
                'amount': amount,
                'period': period
            })

            return order

    @staticmethod
    @log_operation("update_order_status")
    def update_order_status(db: Session, order_id: str, status: str) -> Optional[PaymentOrder]:
        """Update payment order status"""
        with log_context(logger, order_id=order_id, new_status=status):
            order = db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()
            if order:
                old_status = order.status
                order.status = status
                order.updated_at = datetime.now()
                db.commit()
                db.refresh(order)

                logger.info("Updated payment order status", extra={
                    'order_id': order_id,
                    'old_status': old_status,
                    'new_status': status,
                    'user_id': order.user_id
                })
            else:
                logger.warning("Payment order not found for status update", extra={
                    'order_id': order_id,
                    'new_status': status
                })

            return order

    @staticmethod
    @log_operation("create_payment_history")
    def create_payment_history(db: Session, payment_data: Dict[str, Any]) -> PaymentHistory:
        """Create payment history record"""
        with log_context(logger, user_id=payment_data.get('user_id'), order_id=payment_data.get('order_id')):
            payment_history = PaymentHistory(**payment_data)
            db.add(payment_history)
            db.commit()
            db.refresh(payment_history)

            logger.info("Created payment history record", extra={
                'history_id': payment_history.id,
                'user_id': payment_history.user_id,
                'order_id': payment_history.order_id,
                'status': payment_history.status,
                'amount': payment_history.amount
            })

            return payment_history

    @staticmethod
    @log_operation("get_user_payment_history")
    def get_user_payment_history(db: Session, user_id: int, limit: int = 10) -> List[PaymentHistory]:
        """Get payment history for user"""
        with log_context(logger, user_id=user_id, limit=limit):
            history = db.query(PaymentHistory).filter(
                PaymentHistory.user_id == user_id
            ).order_by(desc(PaymentHistory.created_at)).limit(limit).all()

            logger.debug("Retrieved user payment history", extra={
                'user_id': user_id,
                'limit': limit,
                'found_count': len(history)
            })

            return history

    @staticmethod
    @log_operation("get_active_orders")
    def get_active_orders(db: Session, user_id: int) -> List[PaymentOrder]:
        """Get active (pending) orders for user"""
        with log_context(logger, user_id=user_id):
            orders = db.query(PaymentOrder).filter(
                PaymentOrder.user_id == user_id,
                PaymentOrder.status == "pending"
            ).all()

            logger.debug("Retrieved active orders", extra={
                'user_id': user_id,
                'found_count': len(orders)
            })

            return orders

    @staticmethod
    @log_operation("cancel_expired_orders")
    def cancel_expired_orders(db: Session, hours: int = 24) -> int:
        """Cancel orders that have been pending for more than specified hours"""
        with log_context(logger, hours=hours):
            expiry_time = datetime.now() - timedelta(hours=hours)

            expired_orders = db.query(PaymentOrder).filter(
                PaymentOrder.status == "pending",
                PaymentOrder.created_at < expiry_time
            ).all()

            aggregator = LogAggregator(logger, f"cancel_expired_orders_{hours}h")

            for order in expired_orders:
                order.status = "cancelled"
                order.updated_at = datetime.now()
                aggregator.add_item({
                    'order_id': order.order_id,
                    'user_id': order.user_id,
                    'created_at': order.created_at.isoformat()
                }, success=True)

            db.commit()

            aggregator.log_summary()
            logger.info("Cancelled expired orders", extra={
                'hours': hours,
                'cancelled_count': len(expired_orders)
            })

            return len(expired_orders)