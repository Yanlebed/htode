# services/telegram_service/app/payment/wayforpay.py

import hashlib
import requests
import time
import json
import os
import hmac
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Replace with your actual merchant credentials from WayForPay
MERCHANT_ACCOUNT = os.getenv("WAYFORPAY_MERCHANT_LOGIN")
MERCHANT_SECRET = os.getenv("WAYFORPAY_MERCHANT_SECRET")
API_URL = "https://api.wayforpay.com/api"


def generate_signature(data: Dict[str, Any]) -> str:
    """Generate HMAC signature for WayForPay API"""
    keys = sorted(data.keys())
    values = [str(data[key]) for key in keys]
    string = ';'.join(values)

    signature = hmac.new(
        MERCHANT_SECRET.encode('utf-8'),
        string.encode('utf-8'),
        hashlib.md5
    ).hexdigest()

    return signature


def create_payment_request(user_id: int, amount: float, order_id: str, product_name: str) -> Dict[str, Any]:
    """Create payment request data for WayForPay"""
    order_date = int(time.time())

    data = {
        "merchantAccount": MERCHANT_ACCOUNT,
        "merchantDomainName": "yourdomain.com",  # Your domain
        "merchantTransactionType": "CHARGE",
        "merchantTransactionSecureType": "AUTO",
        "orderReference": order_id,
        "orderDate": order_date,
        "amount": amount,
        "currency": "UAH",
        "productName": [product_name],
        "productCount": [1],
        "productPrice": [amount],
        "clientFirstName": f"User{user_id}",
        "clientLastName": "",
        "clientEmail": "",  # You can add user email if available
        "clientPhone": "",  # You can add user phone if available
        "language": "UA",
        "returnUrl": f"https://t.me/YourBotUsername",  # Your bot URL
        "serviceUrl": "https://yourdomain.com/payment/callback"  # Your server callback URL
    }

    data["merchantSignature"] = generate_signature(data)
    return data


def create_payment_form_url(user_id: int, amount: float, period: str = "1 month") -> Optional[str]:
    """
    Create payment URL for the user

    Args:
        user_id: Telegram user ID
        amount: Payment amount in UAH
        period: Subscription period

    Returns:
        Payment form URL or None if failed
    """
    try:
        order_id = f"sub_{user_id}_{int(time.time())}"
        product_name = f"Subscription for {period}"

        # Create payment data
        payment_data = create_payment_request(user_id, amount, order_id, product_name)

        # Send request to WayForPay
        response = requests.post(
            f"{API_URL}/payment",
            json=payment_data,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("reason") == "ok":
                # Store order in database for callback handling
                store_payment_order(user_id, order_id, amount, period)
                return result.get("invoiceUrl")

        logger.error(f"Payment creation failed: {response.text}")
        return None

    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        return None


def store_payment_order(user_id: int, order_id: str, amount: float, period: str):
    """Store payment order in database for later verification"""
    from common.db.database import execute_query

    sql = """
          INSERT INTO payment_orders (user_id, order_id, amount, period, status)
          VALUES (%s, %s, %s, %s, %s) \
          """
    execute_query(sql, [user_id, order_id, amount, period, "pending"])


def verify_payment_callback(callback_data: Dict[str, Any]) -> bool:
    """Verify payment callback from WayForPay"""
    # Verify signature
    received_signature = callback_data.get("merchantSignature")
    if not received_signature:
        return False

    # Remove signature from data for calculation
    verification_data = {k: v for k, v in callback_data.items() if k != "merchantSignature"}

    # Calculate signature
    calculated_signature = generate_signature(verification_data)

    # Compare signatures
    if calculated_signature != received_signature:
        logger.warning("Invalid payment signature")
        return False

    # Verify merchant account
    if callback_data.get("merchantAccount") != MERCHANT_ACCOUNT:
        logger.warning("Invalid merchant account")
        return False

    # Verify transaction status
    if callback_data.get("transactionStatus") != "Approved":
        logger.info(f"Payment not approved: {callback_data.get('transactionStatus')}")
        return False

    return True


def process_successful_payment(order_id: str) -> bool:
    """Process successful payment and update subscription"""
    from common.db.database import execute_query

    # Get order details from database
    sql_order = "SELECT user_id, period FROM payment_orders WHERE order_id = %s"
    order = execute_query(sql_order, [order_id], fetchone=True)

    if not order:
        logger.error(f"Order {order_id} not found")
        return False

    user_id = order["user_id"]
    period = order["period"]

    # Update order status
    sql_update = "UPDATE payment_orders SET status = %s WHERE order_id = %s"
    execute_query(sql_update, ["completed", order_id])

    # Update user subscription
    try:
        from common.db.models import enable_subscription_for_user
        enable_subscription_for_user(user_id)
        logger.info(f"Subscription activated for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to update subscription: {e}")
        return False
