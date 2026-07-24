import os
import logging
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def get_s3_client():
    return boto3.client('s3')

def get_s3_resource():
    return boto3.resource('s3')

def create_bucket(bucket_name, region='us-east-1'):
    """Create an S3 bucket in a specified region"""
    try:
        s3_client = get_s3_client()
        if region == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            location = {'LocationConstraint': region}
            s3_client.create_bucket(Bucket=bucket_name,
                                    CreateBucketConfiguration=location)
        logger.info(f"Created bucket {bucket_name} in {region}")
    except ClientError as e:
        logger.error(e)
        return False
    return True

def upload_file(local_path, bucket_name, s3_key):
    """Upload a file to an S3 bucket"""
    s3_client = get_s3_client()
    try:
        s3_client.upload_file(str(local_path), bucket_name, s3_key)
        logger.info(f"Uploaded {local_path} to s3://{bucket_name}/{s3_key}")
    except ClientError as e:
        logger.error(e)
        return False
    return True

def download_file(bucket_name, s3_key, local_path):
    """Download a file from an S3 bucket"""
    s3_client = get_s3_client()
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        s3_client.download_file(bucket_name, s3_key, str(local_path))
        logger.info(f"Downloaded s3://{bucket_name}/{s3_key} to {local_path}")
    except ClientError as e:
        logger.error(e)
        return False
    return True

def download_directory(bucket_name, s3_prefix, local_dir):
    """Download all files in an S3 prefix to a local directory"""
    s3_resource = get_s3_resource()
    bucket = s3_resource.Bucket(bucket_name)
    local_dir = Path(local_dir)
    
    count = 0
    for obj in bucket.objects.filter(Prefix=s3_prefix):
        if obj.key.endswith('/'):
            continue
        
        # Calculate relative path to preserve directory structure
        relative_path = os.path.relpath(obj.key, s3_prefix)
        # If the prefix itself is a file, relpath will be '.', so handle it:
        if relative_path == '.':
            target_path = local_dir
        else:
            target_path = local_dir / relative_path
            
        target_path.parent.mkdir(parents=True, exist_ok=True)
        bucket.download_file(obj.key, str(target_path))
        count += 1
        
    logger.info(f"Downloaded {count} files from s3://{bucket_name}/{s3_prefix} to {local_dir}")
    return count > 0

def upload_directory(local_dir, bucket_name, s3_prefix):
    """Upload all files in a local directory to an S3 prefix"""
    s3_client = get_s3_client()
    local_dir = Path(local_dir)
    
    count = 0
    for root, dirs, files in os.walk(local_dir):
        for file in files:
            local_path = Path(root) / file
            relative_path = local_path.relative_to(local_dir)
            s3_key = f"{s3_prefix.rstrip('/')}/{relative_path}"
            
            s3_client.upload_file(str(local_path), bucket_name, s3_key)
            count += 1
            
    logger.info(f"Uploaded {count} files from {local_dir} to s3://{bucket_name}/{s3_prefix}")
    return count > 0
