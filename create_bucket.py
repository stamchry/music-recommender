import os
import sys
from dotenv import load_dotenv

# Add src to path so we can import s3_utils
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
import s3_utils

def main():
    load_dotenv()
    bucket_name = os.getenv("AWS_S3_BUCKET")
    region = os.getenv("AWS_REGION", "us-east-1")
    
    if not bucket_name:
        print("Error: AWS_S3_BUCKET not found in environment variables.")
        print("Please add it to your .env file.")
        sys.exit(1)
        
    print(f"Creating bucket '{bucket_name}' in region '{region}'...")
    success = s3_utils.create_bucket(bucket_name, region)
    
    if success:
        print(f"Successfully created bucket {bucket_name}!")
        print("Your pipeline scripts are now configured to use this bucket automatically.")
    else:
        print(f"Failed to create bucket {bucket_name}.")
        print("Check your AWS credentials and make sure the bucket name is globally unique.")

if __name__ == "__main__":
    main()
