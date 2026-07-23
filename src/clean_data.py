import os
import json
import logging
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_data(raw_dir, output_file):
    """
    Load all raw JSON listens, extract relevant fields, and save combined Parquet.
    """
    all_json_files = list(raw_dir.glob("*_listens.json"))
    if not all_json_files:
        logger.error(f"No JSON files found in {raw_dir}")
        return

    all_df = []
    for input_file in all_json_files:
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
        if not df.empty:
            all_df.append(df)
    
    if not all_df:
        logger.warning("No records to process.")
        return
    
    combined_df = pd.concat(all_df, ignore_index=True)
    
    # Handle missing data
    initial_len = len(combined_df)
    combined_df.dropna(subset=["track_name", "artist_name"], inplace=True)
    
    # Fill missing MBIDs with empty strings
    combined_df["recording_mbid"] = combined_df["recording_mbid"].fillna("")
    combined_df["release_mbid"] = combined_df["release_mbid"].fillna("")
    
    logger.info(f"Dropped {initial_len - len(combined_df)} records due to missing track/artist info.")
    
    # Save to Parquet
    logger.info(f"Saving processed data to {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    combined_df.to_parquet(output_file, index=False)

def main():
    load_dotenv()
    
    base_dir = Path(__file__).resolve().parent.parent
    raw_dir = base_dir / "data" / "raw"
    output_file = base_dir / "data" / "processed" / "all_listens.parquet"
    
    clean_data(raw_dir, output_file)

if __name__ == "__main__":
    main()
