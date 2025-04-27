# common/services/user_service.py

import logging
from typing import Dict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session
from common.db.models.user import User
from common.db.repositories.user_repository import UserRepository
from common.messaging.tasks import send_notification

logger = logging.getLogger(__name__)


class UserService:
    @staticmethod
    def get_or_create_user(db: Session, messenger_id: str, messenger_type: str = "telegram") -> int:
        """
        Get or create a user with the specified messenger ID.

        Args:
            db: Database session
            messenger_id: Messenger-specific ID
            messenger_type: Type of messenger (telegram, viber, whatsapp)

        Returns:
            User database ID
        """
        # Get user by messenger ID
        user = UserRepository.get_by_messenger_id(db, messenger_id, messenger_type)

        if user:
            logger.info(f"Found user with {messenger_type} id: {messenger_id}")
            return user.id

        logger.info(f"Creating user with {messenger_type} id: {messenger_id}")

        # Create a new user with free trial period
        free_until = datetime.now() + timedelta(days=7)

        # Create user with the appropriate messenger ID
        user = UserRepository.create_messenger_user(db, messenger_id, messenger_type, free_until)
        return user.id

    @staticmethod
    def check_expiring_subscriptions(db: Session) -> Dict[str, int]:
        """
        Check for expiring subscriptions and send reminders.

        Args:
            db: Database session

        Returns:
            Dictionary with counts of reminders sent
        """

        reminders_sent = 0

        # Check for subscriptions expiring in 3, 2, and 1 days
        for days in [3, 2, 1]:
            today = datetime.now().date()
            target_date = today + timedelta(days=days)

            # Get users whose subscription expires on the target date
            # Using ORM instead of raw SQL
            users = db.query(User).filter(
                func.date(User.subscription_until) == target_date
            ).all()

            for user in users:
                user_id = user.id
                end_date = user.subscription_until.strftime("%d.%m.%Y")

                # Determine template based on days remaining
                if days == 1:
                    template = (
                        "⚠️ Ваша підписка закінчується завтра!\n\n"
                        "Дата закінчення: {end_date}\n\n"
                        "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                    )
                else:
                    # Determine plural form
                    days_word = "день" if days == 1 else "дні" if days < 5 else "днів"
                    template = (
                        "⚠️ Нагадування про підписку\n\n"
                        "Ваша підписка закінчується через {days} "
                        "{days_word}.\n"
                        "Дата закінчення: {end_date}\n\n"
                        "Щоб продовжити користуватися сервісом, оновіть підписку."
                    )

                # Send notification
                send_notification.delay(
                    user_id=user_id,
                    template=template,
                    data={
                        "days": days,
                        "days_word": days_word,
                        "end_date": end_date
                    }
                )
                reminders_sent += 1

        # Notify on day of expiration
        users_today = db.query(User).filter(
            func.date(User.subscription_until) == today
        ).all()

        for user in users_today:
            user_id = user.id
            end_date = user.subscription_until.strftime("%d.%m.%Y %H:%M")

            send_notification.delay(
                user_id=user_id,
                template=(
                    "⚠️ Ваша підписка закінчується сьогодні!\n\n"
                    "Час закінчення: {end_date}\n\n"
                    "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                ),
                data={"end_date": end_date}
            )
            reminders_sent += 1

        return {"reminders_sent": reminders_sent}