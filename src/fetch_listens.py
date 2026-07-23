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
        response = requests.get(base_url, headers=headers, params=params)
        response.raise_for_status()
        
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
    load_dotenv()
    username = os.getenv("LISTENBRAINZ_USERNAME")
    token = os.getenv("LISTENBRAINZ_TOKEN")
    
    if not username:
        logger.error("LISTENBRAINZ_USERNAME not found in environment.")
        return
        
    logger.info(f"Starting fetch for user: {username}")
    
    listens = fetch_listens(username, token, max_pages=5)
    
    # Save to data/raw
    output_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / f"{username}_listens.json"
    with open(output_file, "w") as f:
        json.dump(listens, f, indent=2)
        
    logger.info(f"Saved {len(listens)} listens to {output_file}")

if __name__ == "__main__":
    main()
