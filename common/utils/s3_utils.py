# common/utils/s3_utils.py
import logging
import boto3
from common.config import AWS_CONFIG
from common.utils.request_utils import make_request

logger = logging.getLogger(__name__)

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_CONFIG["access_key"],
    aws_secret_access_key=AWS_CONFIG["secret_key"],
    region_name=AWS_CONFIG["region"]
)


def _upload_image_to_s3(image_url, ad_unique_id):
    """
    Downloads the image from `image_url` and uploads to S3.
    Returns the final S3 (or CloudFront) URL if successful, else None.
    """
    try:
        # 1) Download image using our retry utility
        response = make_request(
            image_url,
            method='get',
            timeout=10,
            retries=3,
            raise_for_status=False
        )

        if not response or response.status_code != 200:
            logger.error(
                f"Failed to download image from {image_url}, status: {response.status_code if response else 'No response'}")
            return None

        image_data = response.content

        # 2) Create a unique key for S3
        image_id = image_url.split("/")[-1].split('.')[0]
        file_extension = image_url.split(".")[-1][:4]  # naive approach, e.g. "jpg", "png", "webp"
        s3_key = f"{AWS_CONFIG['s3_prefix']}{ad_unique_id}_{image_id}.{file_extension}"

        # 3) Upload to S3
        s3_client.put_object(
            Bucket=AWS_CONFIG["s3_bucket"],
            Key=s3_key,
            Body=image_data,
            ContentType="image/jpeg",  # or detect from file_extension
        )

        # 4) Build final URL
        if AWS_CONFIG["cloudfront_domain"]:
            final_url = f"{AWS_CONFIG['cloudfront_domain']}/{s3_key}"
        else:
            final_url = f"https://{AWS_CONFIG['s3_bucket']}.s3.amazonaws.com/{s3_key}"

        return final_url

    except Exception as e:
        logger.error(f"Failed to upload image to S3: {e}")
        return None