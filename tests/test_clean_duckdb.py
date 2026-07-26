import json
import pandas as pd
from pathlib import Path
from src.clean_duckdb import ingest_into_staging_db, compile_staged_to_parquet, clean_and_select_features

def test_duckdb_staged_dedupe(tmp_path):
    # Create two dummy JSON files simulating overlapping daily dumps with duplicate events
    dump1 = [
        {
            "user_name": "listener_alpha",
            "listened_at": 1700000000,
            "track_metadata": {
                "track_name": "Song One (Remastered)",
                "artist_name": "Artist One  ",
                "release_name": "Album A",
                "additional_info": {"recording_mbid": "rec-123"}
            }
        },
        {
            "user_name": "listener_alpha",
            "listened_at": 1700000100,
            "track_metadata": {
                "track_name": "Song Two",
                "artist_name": "Artist One",
                "release_name": "Album A"
            }
        }
    ]
    
    # Dump 2 contains a duplicate of the first scrobble + a new scrobble
    dump2 = [
        {
            "user_name": "listener_alpha",
            "listened_at": 1700000000,
            "track_metadata": {
                "track_name": "Song One (Remastered)",
                "artist_name": "Artist One",
                "release_name": "Album A",
                "additional_info": {"recording_mbid": "rec-123"}
            }
        },
        {
            "user_name": "listener_alpha",
            "listened_at": 1700000200,
            "track_metadata": {
                "track_name": "Song Three",
                "artist_name": "Artist One"
            }
        }
    ]
    
    raw_dir = tmp_path / "raw_dumps"
    raw_dir.mkdir()
    file1 = raw_dir / "day1_listens.json"
    file2 = raw_dir / "day2_listens.json"
    
    with open(file1, "w") as f:
        json.dump(dump1, f)
    with open(file2, "w") as f:
        json.dump(dump2, f)
        
    staging_db = tmp_path / "staging.duckdb"
    output_parquet = tmp_path / "final.parquet"
    
    # Ingest day 1 and day 2 into staging DB
    count1 = ingest_into_staging_db(str(file1), staging_db)
    count2 = ingest_into_staging_db(str(file2), staging_db)
    
    assert count1 == 1
    assert count2 == 1
    
    # Compile to parquet with minimal thresholds (min 1 play)
    compile_staged_to_parquet(staging_db, output_parquet, min_user_plays=1, min_artist_plays=1)
    
    assert output_parquet.exists()
    
    df = pd.read_parquet(output_parquet)
    
    # Out of 4 raw events across 2 dumps, 1 duplicate should be eliminated, leaving 3 unique plays
    assert len(df) == 3
    assert set(df["track_name"].tolist()) == {"Song One", "Song Two", "Song Three"}
    assert all(df["artist_name"] == "Artist One")
