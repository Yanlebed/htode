# services/webapps/mini_webapp.py
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime

from flask import Flask, request, render_template_string, jsonify

logger = logging.getLogger(__name__)

# Get these from environment variables
MERCHANT_ACCOUNT = os.getenv("WAYFORPAY_MERCHANT_ACCOUNT")
MERCHANT_SECRET = os.getenv("WAYFORPAY_MERCHANT_SECRET")
app = Flask(__name__)

GALLERY_HTML = """
<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8" />
  <title>Фотогалерея</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 15px;
    }
    h2 {
      margin-bottom: 10px;
    }
    /* The images display at maximum width */
    .gallery-img {
      width: 100%;         /* Full width of container */
      max-width: 100%;     /* No overflow horizontally */
      margin-bottom: 20px;
      cursor: zoom-in;     /* Indicate clickable zoom */
    }
    /* The Modal (background overlay) */
    .modal {
      display: none;       /* Hidden by default */
      position: fixed;     /* Stay in place */
      z-index: 9999;       /* On top */
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      overflow: auto;
      background-color: rgba(0,0,0,0.8); /* black w/ opacity */
    }
    /* Modal Image styling */
    .modal-content {
      display: block;
      margin: auto;
      max-width: 90%;
      max-height: 90%;
      box-shadow: 0 0 10px #000;
    }
    /* Close button (top-right) */
    .close {
      position: absolute;
      top: 30px;
      right: 45px;
      color: #fff;
      font-size: 40px;
      font-weight: bold;
      cursor: pointer;
    }
    .close:hover,
    .close:focus {
      color: #bbb;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <h2>Фотогалерея</h2>
  <div id="gallery"></div>

  <!-- The Modal -->
  <div id="myModal" class="modal">
    <span class="close" id="closeBtn">&times;</span>
    <img class="modal-content" id="modalImg">
  </div>

  <script>
    const urlParams = new URLSearchParams(window.location.search);
    const imagesParam = urlParams.get("images"); // e.g. "https://...,https://..."
    const galleryDiv = document.getElementById("gallery");
    if (imagesParam) {
      const imgArray = imagesParam.split(",");
      imgArray.forEach(url => {
        const img = document.createElement("img");
        img.src = url.trim();
        img.className = "gallery-img";
        // On click => open modal
        img.onclick = function() {
          openModal(url.trim());
        };
        galleryDiv.appendChild(img);
      });
    } else {
      galleryDiv.textContent = "Немає зображень.";
    }

    // Modal logic
    const modal = document.getElementById("myModal");
    const modalImg = document.getElementById("modalImg");
    const closeBtn = document.getElementById("closeBtn");

    function openModal(imageUrl) {
      modal.style.display = "block";
      modalImg.src = imageUrl;
    }

    closeBtn.onclick = function() {
      modal.style.display = "none";
    };

    // Close the modal if user clicks outside the image
    window.onclick = function(event) {
      if (event.target === modal) {
        modal.style.display = "none";
      }
    }
  </script>
</body>
</html>
"""

PHONE_HTML = """
<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <title>Телефони</title>
  <style>
    body {
      background: #FFF;    /* White page background */
      color: #000;         /* Black default text */
      margin: 15px;
      font-family: Arial, sans-serif;
    }
    h2 {
      margin-bottom: 10px;
    }
    .phone-list {
      /* If you want to control max width of the entire content */
      max-width: 600px;
      margin: 0 auto;    /* Center horizontally */
    }
    /* Each phone link is a block with white background, black text */
    a.phone-link {
      display: block;
      background: #FFF;   /* White background for each link */
      color: #000;        /* Black text */
      text-decoration: none;
      font-size: 20px;    /* Adjust as needed */
      padding: 10px;
      border: 1px solid #AAA;
      border-radius: 4px;
      margin: 10px 0;
      width: 100%;
      box-sizing: border-box; /* So padding doesn't exceed width */
    }
    a.phone-link:hover {
      background: #f9f9f9; /* Slight hover effect */
    }
  </style>
</head>
<body>
  <h2>Телефони</h2>
  <div class="phone-list" id="phone-list"></div>
  <script>
    const urlParams = new URLSearchParams(window.location.search);
    const numbersParam = urlParams.get("numbers"); // e.g. "380999999999,380971234567"

    const phoneDiv = document.getElementById("phone-list");
    if (numbersParam) {
      const phoneArray = numbersParam.split(",");
      phoneArray.forEach(num => {
        const link = document.createElement("a");
        link.href = "tel:" + num.trim();   // Tapping opens dialer
        link.className = "phone-link";
        link.textContent = num.trim();
        phoneDiv.appendChild(link);
      });
    } else {
      phoneDiv.textContent = "Немає телефонів.";
    }
  </script>
</body>
</html>
"""


@app.route("/gallery")
def gallery_route():
    return render_template_string(GALLERY_HTML)


@app.route("/phones")
def phones_route():
    return render_template_string(PHONE_HTML)


@app.route("/health")
def health_check():
    """Simple health check endpoint for monitoring"""
    return jsonify({"status": "ok"})


def verify_wayforpay_signature(data):
    """Verify WayForPay callback signature"""
    if not MERCHANT_SECRET:
        logger.error("Missing WAYFORPAY_MERCHANT_SECRET environment variable")
        return False

    # Extract the signature from the data
    received_signature = data.get("merchantSignature")
    if not received_signature:
        logger.error("Missing merchantSignature in callback data")
        return False

    # Remove the signature from the data
    verification_data = {k: v for k, v in data.items() if k != "merchantSignature"}

    # Sort parameters by key
    keys = sorted(verification_data.keys())
    values = [str(verification_data[key]) for key in keys]
    string_to_sign = ";".join(values)

    # Generate signature
    calculated_signature = hmac.new(
        MERCHANT_SECRET.encode('utf-8'),
        string_to_sign.encode('utf-8'),
        hashlib.md5
    ).hexdigest()

    # Compare signatures
    if calculated_signature != received_signature:
        logger.error(f"Invalid signature. Expected: {calculated_signature}, Received: {received_signature}")
        return False

    # Verify merchant account
    if data.get("merchantAccount") != MERCHANT_ACCOUNT:
        logger.error(f"Invalid merchant account. Expected: {MERCHANT_ACCOUNT}, Received: {data.get('merchantAccount')}")
        return False

    return True


@app.route("/payment/callback", methods=["POST"])
def payment_callback():
    """
    Handle WayForPay payment callbacks with enhanced security and user notifications
    """
    try:
        # Get callback data from request
        callback_data = request.get_json()
        if not callback_data:
            logger.error("No JSON data in callback")
            return jsonify({"status": "error", "message": "Invalid data format"}), 400

        logger.info(f"Received payment callback: {json.dumps(callback_data)}")

        # Verify the signature and merchant account
        if not verify_wayforpay_signature(callback_data):
            logger.error("Payment signature verification failed")
            return jsonify({"status": "error", "message": "Signature verification failed"}), 400

        # Get order reference
        order_id = callback_data.get("orderReference")
        if not order_id:
            logger.error("Missing orderReference in callback")
            return jsonify({"status": "error", "message": "Missing order reference"}), 400

        # Get transaction status
        transaction_status = callback_data.get("transactionStatus")
        if transaction_status != "Approved":
            logger.info(f"Payment not approved: {transaction_status}")

            # Update payment status in database even for non-approved payments
            try:
                from common.db.database import execute_query

                sql_update = """
                             UPDATE payment_orders
                             SET status = %s
                             WHERE order_id = %s \
                             """
                execute_query(sql_update, [transaction_status.lower(), order_id])

                # Store in payment history
                sql_history = """
                              INSERT INTO payment_history
                              (user_id, order_id, amount, subscription_period, status, transaction_id, card_mask, \
                               payment_details)
                              SELECT user_id, \
                                     order_id, \
                                     amount, \
                                     period, \
                                     %s, \
                                     %s, \
                                     %s, \
                                     %s
                              FROM payment_orders
                              WHERE order_id = %s \
                              """
                execute_query(sql_history, [
                    transaction_status.lower(),
                    callback_data.get("authCode", ""),
                    callback_data.get("cardPan", ""),
                    json.dumps(callback_data),
                    order_id
                ])
            except Exception as e:
                logger.error(f"Error updating non-approved payment status: {e}")

            return jsonify({"status": "acknowledged", "message": "Non-approved status noted"}), 200

        # Process the approved payment
        try:
            # Import here to avoid circular imports
            import sys
            import time
            sys.path.append('/app')  # Make sure app directory is in path

            from common.db.database import execute_query

            # Get order details from database
            sql_order = """
                        SELECT user_id, amount, period
                        FROM payment_orders
                        WHERE order_id = %s \
                        """
            order_data = execute_query(sql_order, [order_id], fetchone=True)

            if not order_data:
                logger.error(f"Order not found: {order_id}")
                return jsonify({"status": "error", "message": "Order not found"}), 404

            user_id = order_data["user_id"]
            period = order_data["period"]

            # Determine subscription duration in days
            period_days = 30  # Default to 30 days
            if period == "3months":
                period_days = 90
            elif period == "6months":
                period_days = 180
            elif period == "12months":
                period_days = 365

            # Update payment status
            sql_update = """
                         UPDATE payment_orders
                         SET status = 'completed'
                         WHERE order_id = %s \
                         """
            execute_query(sql_update, [order_id])

            # Store in payment history
            sql_history = """
                          INSERT INTO payment_history
                          (user_id, order_id, amount, subscription_period, status, transaction_id, card_mask, \
                           payment_details)
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s) \
                          """
            execute_query(sql_history, [
                user_id,
                order_id,
                callback_data.get("amount", order_data["amount"]),
                period,
                "completed",
                callback_data.get("authCode", ""),
                callback_data.get("cardPan", ""),
                json.dumps(callback_data)
            ])

            # Check if user already has an active subscription
            sql_check = """
                        SELECT subscription_until
                        FROM users
                        WHERE id = %s \
                        """
            user_sub = execute_query(sql_check, [user_id], fetchone=True)

            # Calculate new subscription end date
            if user_sub and user_sub["subscription_until"] and user_sub["subscription_until"] > datetime.now():
                # Extend existing subscription
                sql_subscription = """
                                   UPDATE users
                                   SET subscription_until = subscription_until + interval '%s days'
                                   WHERE id = %s
                                       RETURNING subscription_until \
                                   """
            else:
                # Set new subscription
                sql_subscription = """
                                   UPDATE users
                                   SET subscription_until = NOW() + interval '%s days'
                                   WHERE id = %s
                                       RETURNING subscription_until \
                                   """

            # Update subscription
            sub_result = execute_query(sql_subscription, [period_days, user_id], fetchone=True)
            logger.info(f"Updated subscription for user {user_id} until {sub_result['subscription_until']}")

            # Get telegram_id for notification
            sql_telegram = """
                           SELECT telegram_id
                           FROM users
                           WHERE id = %s \
                           """
            telegram_result = execute_query(sql_telegram, [user_id], fetchone=True)

            if telegram_result and telegram_result["telegram_id"]:
                # Format the date for display
                sub_date = sub_result["subscription_until"].strftime("%d.%m.%Y")

                # Send success notification via Celery task
                from common.celery_app import celery_app
                celery_app.send_task(
                    'telegram_service.app.tasks.send_subscription_notification',
                    args=[
                        telegram_result["telegram_id"],
                        "payment_success",
                        {
                            "order_id": order_id,
                            "amount": callback_data.get("amount", order_data["amount"]),
                            "subscription_until": sub_date
                        }
                    ]
                )

            # Return success response with expected format for WayForPay
            return jsonify({
                "orderReference": order_id,
                "status": "accept",
                "time": int(time.time())
            }), 200

        except Exception as e:
            logger.exception(f"Error processing payment: {e}")
            return jsonify({"status": "error", "message": "Error processing payment"}), 500

    except Exception as e:
        logger.exception(f"Error in payment callback: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # For local dev
    app.run(host="0.0.0.0", port=8080, debug=True)
