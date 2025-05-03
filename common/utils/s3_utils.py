# common/utils/s3_utils.py
import time
import mimetypes
import boto3
import redis

from botocore.exceptions import ClientError
from common.config import AWS_CONFIG, REDIS_URL
from common.utils.unified_request_utils import make_request
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the common utils logger
from . import logger

# Initialize S3 client using config
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_CONFIG['access_key'],
    aws_secret_access_key=AWS_CONFIG['secret_key'],
    region_name=AWS_CONFIG['region']
)

redis_client = redis.from_url(REDIS_URL)


@log_operation("detect_content_type")
def detect_content_type(image_url, file_extension):
    """
    Detect the content type based on the file extension.
    """
    with log_context(logger, file_extension=file_extension, image_url=image_url[:50]):
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

        logger.debug("Detected content type", extra={
            'content_type': content_type,
            'file_extension': file_extension
        })

        return content_type


@log_operation("upload_image_to_s3")
def _upload_image_to_s3(image_url, ad_unique_id, max_retries=3, retry_delay=1):
    """
    Downloads the image from `image_url` and uploads to S3.
    """
    with log_context(logger, image_url=image_url[:50], ad_id=ad_unique_id):
        if not image_url:
            logger.warning("Empty image URL provided")
            return None

        if not ad_unique_id:
            logger.warning("Empty ad_unique_id provided")
            return None

        logger.info("Starting image upload to S3", extra={
            'image_url': image_url[:50],
            'ad_id': ad_unique_id
        })

        aggregator = LogAggregator(logger, f"upload_image_to_s3_{ad_unique_id}")

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
                logger.error("Failed to download image", extra={
                    'image_url': image_url[:50],
                    'status_code': response.status_code if response else 'No response'
                })
                aggregator.add_error("Download failed", {'url': image_url[:50]})
                return None

            image_data = response.content

            # 2) Extract file details and create S3 key
            try:
                image_parts = image_url.split("/")
                filename = image_parts[-1]

                # Handle URLs with query parameters
                if '?' in filename:
                    filename = filename.split('?')[0]

                # Get the base name without extension
                if '.' in filename:
                    base_name, file_extension = filename.rsplit('.', 1)
                else:
                    base_name = filename
                    file_extension = "jpg"

                # Sanitize the base name
                base_name = ''.join(c for c in base_name if c.isalnum() or c in '_-')

                # Create S3 key
                s3_key = f"{AWS_CONFIG['s3_prefix']}{ad_unique_id}_{base_name}.{file_extension}"

            except Exception as e:
                logger.error("Error creating S3 key", exc_info=True, extra={
                    'image_url': image_url[:50],
                    'error_type': type(e).__name__
                })
                s3_key = f"{AWS_CONFIG['s3_prefix']}{ad_unique_id}_{hash(image_url)}.jpg"

            # 3) Determine content type
            content_type = detect_content_type(image_url, file_extension)

            # 4) Upload to S3 with retries
            for attempt in range(max_retries):
                try:
                    with log_context(logger, attempt=attempt + 1, s3_key=s3_key):
                        s3_client.put_object(
                            Bucket=AWS_CONFIG['s3_bucket'],
                            Key=s3_key,
                            Body=image_data,
                            ContentType=content_type,
                        )
                        logger.debug("Successfully uploaded to S3", extra={'s3_key': s3_key})
                        aggregator.add_item({'s3_key': s3_key}, success=True)
                        break  # Success

                except ClientError as e:
                    if attempt < max_retries - 1:
                        current_delay = retry_delay * (2 ** attempt)
                        logger.warning("S3 upload failed, retrying", extra={
                            'attempt': attempt + 1,
                            'max_retries': max_retries,
                            'delay': current_delay,
                            'error': str(e),
                            'error_type': type(e).__name__
                        })
                        time.sleep(current_delay)
                    else:
                        logger.error("S3 upload failed after retries", exc_info=True, extra={
                            'attempts': max_retries,
                            'error_type': type(e).__name__
                        })
                        aggregator.add_error("S3 upload failed", {'error': str(e)})
                        return None

            # 5) Build final URL
            if AWS_CONFIG['cloudfront_domain']:
                final_url = f"{AWS_CONFIG['cloudfront_domain']}/{s3_key}"
            else:
                final_url = f"https://{AWS_CONFIG['s3_bucket']}.s3.amazonaws.com/{s3_key}"

            logger.info("Successfully uploaded image", extra={
                'final_url': final_url[:50],
                's3_key': s3_key
            })

            aggregator.log_summary()
            return final_url

        except Exception as e:
            logger.error("Unexpected error uploading image", exc_info=True, extra={
                'image_url': image_url[:50],
                'error_type': type(e).__name__
            })
            aggregator.add_error("Unexpected error", {'error': str(e)})
            aggregator.log_summary()
            return None