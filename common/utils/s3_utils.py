# common/utils/s3_utils.py
import logging
import time
import mimetypes
import boto3
from botocore.exceptions import ClientError
from common.config import AWS_CONFIG
from common.utils.request_utils import make_request

logger = logging.getLogger(__name__)

# Initialize S3 client using config
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_CONFIG['access_key'],
    aws_secret_access_key=AWS_CONFIG['secret_key'],
    region_name=AWS_CONFIG['region']
)


def detect_content_type(image_url, file_extension):
    """
    Detect the content type based on the file extension.

    Args:
        image_url: The URL of the image
        file_extension: The file extension from the URL

    Returns:
        The detected content type (MIME type)
    """
    # Try to guess from URL first
    content_type = mimetypes.guess_type(image_url)[0]

    # If that fails, try from extension
    if not content_type:
        if file_extension.lower() in ['jpg', 'jpeg']:
            content_type = 'image/jpeg'
        elif file_extension.lower() == 'png':
            content_type = 'image/png'
        elif file_extension.lower() == 'webp':
            content_type = 'image/webp'
        elif file_extension.lower() == 'gif':
            content_type = 'image/gif'
        else:
            # Default to JPEG if we can't determine
            content_type = 'image/jpeg'

    return content_type


def _upload_image_to_s3(image_url, ad_unique_id, max_retries=3, retry_delay=1):
    """
    Downloads the image from `image_url` and uploads to S3.
    Returns the final S3 (or CloudFront) URL if successful, else None.

    Args:
        image_url: URL of the image to download
        ad_unique_id: Unique ID of the ad (for naming the image)
        max_retries: Maximum number of retry attempts for failed operations
        retry_delay: Initial delay between retries (will increase exponentially)

    Returns:
        Final S3/CloudFront URL of the uploaded image, or None if failed
    """
    if not image_url:
        logger.warning("Empty image URL provided")
        return None

    if not ad_unique_id:
        logger.warning("Empty ad_unique_id provided")
        return None

    logger.info(f"Uploading image from {image_url} for ad {ad_unique_id}")

    try:
        # 1) Download image with our retry utility
        response = make_request(
            url=image_url,
            method='get',
            timeout=10,
            retries=max_retries,
            raise_for_status=False
        )

        if not response or response.status_code != 200:
            logger.error(
                f"Failed to download image from {image_url}, status: {response.status_code if response else 'No response'}")
            return None

        image_data = response.content

        # 2) Extract file details and create S3 key
        try:
            # Parse URL paths like "/path/to/image_123.jpg" or just "image_123.jpg"
            image_parts = image_url.split("/")
            filename = image_parts[-1]  # Get the last part of the URL

            # Handle URLs with query parameters
            if '?' in filename:
                filename = filename.split('?')[0]

            # Get the base name without extension
            if '.' in filename:
                base_name, file_extension = filename.rsplit('.', 1)
            else:
                # If no extension in URL, use a fallback
                base_name = filename
                file_extension = "jpg"

            # Sanitize the base name to ensure it's a valid S3 key
            base_name = ''.join(c for c in base_name if c.isalnum() or c in '_-')

            # Create a unique S3 key with the ad_unique_id to avoid conflicts
            s3_key = f"{AWS_CONFIG['s3_prefix']}{ad_unique_id}_{base_name}.{file_extension}"
        except Exception as e:
            logger.error(f"Error creating S3 key from URL {image_url}: {e}")
            # Use a hash of the URL as a fallback filename
            s3_key = f"{AWS_CONFIG['s3_prefix']}{ad_unique_id}_{hash(image_url)}.jpg"

        # 3) Determine content type
        content_type = detect_content_type(image_url, file_extension)

        # 4) Upload to S3 with retries
        for attempt in range(max_retries):
            try:
                s3_client.put_object(
                    Bucket=AWS_CONFIG['s3_bucket'],
                    Key=s3_key,
                    Body=image_data,
                    ContentType=content_type,
                )
                break  # Success, exit retry loop
            except ClientError as e:
                if attempt < max_retries - 1:
                    # Calculate exponential backoff delay
                    current_delay = retry_delay * (2 ** attempt)
                    logger.warning(
                        f"S3 upload attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {current_delay}s")
                    time.sleep(current_delay)
                else:
                    logger.error(f"S3 upload failed after {max_retries} attempts: {e}")
                    return None

        # 5) Build final URL
        if AWS_CONFIG['cloudfront_domain']:
            final_url = f"{AWS_CONFIG['cloudfront_domain']}/{s3_key}"
        else:
            final_url = f"https://{AWS_CONFIG['s3_bucket']}.s3.amazonaws.com/{s3_key}"

        logger.info(f"Successfully uploaded image to {final_url}")
        return final_url

    except Exception as e:
        logger.exception(f"Unexpected error uploading image to S3: {e}")
        return None


def get_image_urls_for_ad(ad_id, max_images=5):
    """
    Get S3 image URLs for an ad from the database.

    Args:
        ad_id: The database ID of the ad
        max_images: Maximum number of images to return

    Returns:
        List of image URLs or empty list if no images found
    """
    from common.db.database import execute_query

    try:
        sql = """
        SELECT image_url FROM ad_images 
        WHERE ad_id = %s 
        ORDER BY id 
        LIMIT %s
        """
        rows = execute_query(sql, [ad_id, max_images], fetch=True)
        if rows:
            return [row['image_url'] for row in rows]
        return []
    except Exception as e:
        logger.error(f"Error retrieving image URLs for ad {ad_id}: {e}")
        return []


def delete_s3_image(image_url):
    """
    Delete an image from S3 by its URL.

    Args:
        image_url: The full URL of the image to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        # Extract the S3 key from the URL
        if AWS_CONFIG['cloudfront_domain'] and AWS_CONFIG['cloudfront_domain'] in image_url:
            # CloudFront URL
            s3_key = image_url.replace(f"{AWS_CONFIG['cloudfront_domain']}/", "")
        else:
            # Direct S3 URL
            s3_key = image_url.replace(f"https://{AWS_CONFIG['s3_bucket']}.s3.amazonaws.com/", "")

        # Delete the object
        s3_client.delete_object(
            Bucket=AWS_CONFIG['s3_bucket'],
            Key=s3_key
        )
        logger.info(f"Successfully deleted image from S3: {s3_key}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete image from S3: {e}")
        return False