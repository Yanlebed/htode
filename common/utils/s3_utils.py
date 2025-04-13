import logging
import requests
import boto3

S3_BUCKET = "htodebucket"  # os.getenv("AWS_S3_BUCKET", "your-bucket-name")
S3_PREFIX = "ads-images/"  # os.getenv("AWS_S3_BUCKET_PREFIX", "")
CLOUDFRONT_DOMAIN = "https://d3h86hbbdu2c7h.cloudfront.net"  # os.getenv("AWS_CLOUDFRONT_DOMAIN")  # if you have one
# DDOS protection

s3_client = boto3.client(
    's3',
    aws_access_key_id="AKIAS74TMCYOZMLDIA6K",  # os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key="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",  # os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name="eu-west-1"  # os.getenv("AWS_DEFAULT_REGION", "us-east-1")
)

logger = logging.getLogger(__name__)


def _upload_image_to_s3(image_url, ad_unique_id):
    """
    Downloads the image from `image_url` and uploads to S3.
    Returns the final S3 (or CloudFront) URL if successful, else None.
    """
    try:
        # 1) Download image
        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        image_data = resp.content

        # 2) Create a unique key for S3
        # E.g. "ads-images/<ad_id>_<image_id>.jpg"
        image_id = image_url.split("/")[-1].split('.')[0]
        file_extension = image_url.split(".")[-1][:4]  # naive approach, e.g. "jpg", "png", "webp"
        s3_key = f"{S3_PREFIX}{ad_unique_id}_{image_id}.{file_extension}"

        # 3) Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=image_data,
            ContentType="image/jpeg",  # or detect from file_extension
            # ACL='public-read'  # or your desired ACL/policy
        )

        # 4) Build final URL
        if CLOUDFRONT_DOMAIN:
            final_url = f"{CLOUDFRONT_DOMAIN}/{s3_key}"
        else:
            final_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}"

        return final_url

    except Exception as e:
        logger.error(f"Failed to upload image to S3: {e}")
        return None
