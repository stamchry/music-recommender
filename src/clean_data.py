import os
import json
import logging
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_data(input_file, output_file):
    """
    Load raw JSON listens, extract relevant fields, and save to Parquet.
    """
    logger.info(f"Loading raw data from {input_file}")
    with open(input_file, "r") as f:
        listens = json.load(f)
        
    records = []
    for listen in listens:
        track_meta = listen.get("track_metadata", {})
        add_meta = track_meta.get("additional_info", {})
        
        record = {
            "user_name": listen.get("user_name"),
            "listened_at": listen.get("listened_at"),
            "track_name": track_meta.get("track_name"),
            "artist_name": track_meta.get("artist_name"),
            "release_name": track_meta.get("release_name"),
            "recording_mbid": add_meta.get("recording_mbid"),
            "artist_mbids": add_meta.get("artist_mbids", []),
            "release_mbid": add_meta.get("release_mbid")
        }
        records.append(record)
        
    df = pd.DataFrame(records)
    
    if df.empty:
        logger.warning("No records to process.")
        return
    
    # Handle missing data
    # Drop rows without an artist or track
    initial_len = len(df)
    df.dropna(subset=["track_name", "artist_name"], inplace=True)
    
    # Fill missing MBIDs with empty strings
    df["recording_mbid"] = df["recording_mbid"].fillna("")
    df["release_mbid"] = df["release_mbid"].fillna("")
    
    logger.info(f"Dropped {initial_len - len(df)} records due to missing track/artist info.")
    
    # Save to Parquet
    logger.info(f"Saving processed data to {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_file, index=False)

def main():
    load_dotenv()
    username = os.getenv("LISTENBRAINZ_USERNAME")
    
    if not username:
        logger.error("LISTENBRAINZ_USERNAME not found in environment.")
        return
        
    base_dir = Path(__file__).resolve().parent.parent
    input_file = base_dir / "data" / "raw" / f"{username}_listens.json"
    output_file = base_dir / "data" / "processed" / f"{username}_listens.parquet"
    
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return
        
    clean_data(input_file, output_file)

if __name__ == "__main__":
    main()
