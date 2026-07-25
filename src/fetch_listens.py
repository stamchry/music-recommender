import os
import json
import time
import logging
from pathlib import Path
import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_listens(username, token=None, max_pages=5):
    """
    Fetch listen history for a ListenBrainz user.
    """
    base_url = f"https://api.listenbrainz.org/1/user/{username}/listens"
    headers = {}
    if token:
        headers["Authorization"] = f"Token {token}"
        
    all_listens = []
    max_ts = None
    
    for page in range(max_pages):
        params = {"count": 100}
        if max_ts:
            params["max_ts"] = max_ts
            
        logger.info(f"Fetching page {page + 1} for {username}...")
        
        for attempt in range(3):
            try:
                response = requests.get(base_url, headers=headers, params=params, timeout=15)
                response.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                time.sleep(2 ** attempt)
        else:
            logger.error(f"Failed to fetch page {page + 1} for {username} after 3 attempts. Skipping rest of user.")
            break
        
        data = response.json()
        payload = data.get("payload", {})
        listens = payload.get("listens", [])
        
        if not listens:
            logger.info("No more listens found.")
            break
            
        all_listens.extend(listens)
        max_ts = listens[-1].get("listened_at")
        
        # Respect rate limits (1 request per second is safe)
        time.sleep(1)
        
    return all_listens

def main():
    load_dotenv(override=True)
    # Support multiple users via comma-separated string, fallback to single username
    usernames_env = os.getenv("LISTENBRAINZ_USERNAMES", os.getenv("LISTENBRAINZ_USERNAME"))
    token = os.getenv("LISTENBRAINZ_TOKEN")
    
    if not usernames_env:
        logger.error("LISTENBRAINZ_USERNAMES not found in environment.")
        return
        
    usernames = [u.strip() for u in usernames_env.split(",") if u.strip()]
    
    output_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for username in usernames:
        logger.info(f"Starting fetch for user: {username}")
        listens = fetch_listens(username, token, max_pages=20)
        
        output_file = output_dir / f"{username}_listens.json"
        with open(output_file, "w") as f:
            json.dump(listens, f, indent=2)
            
        logger.info(f"Saved {len(listens)} listens to {output_file}")
        
        bucket = os.getenv("AWS_S3_BUCKET")
        if bucket:
            from s3_utils import upload_file
            s3_key = f"data/raw/{output_file.name}"
            upload_file(output_file, bucket, s3_key)

if __name__ == "__main__":
    main()
