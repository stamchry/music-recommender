import json
import pandas as pd
from pathlib import Path
from src.clean_data import clean_data

def test_clean_data(tmp_path):
    raw_data = [
        {
            "user_name": "test_user",
            "listened_at": 1620000000,
            "track_metadata": {
                "track_name": "Song A",
                "artist_name": "Artist A",
                "additional_info": {
                    "recording_mbid": "1234"
                }
            }
        },
        {
            "user_name": "test_user",
            "listened_at": 1620000100,
            "track_metadata": {
            }
        }
    ]
    
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    input_file = raw_dir / "test_user_listens.json"
    with open(input_file, "w") as f:
        json.dump(raw_data, f)
        
    output_file = tmp_path / "processed.parquet"
    
    clean_data(raw_dir, output_file)
    
    assert output_file.exists()
    
    df = pd.read_parquet(output_file)
    assert len(df) == 1
    assert df.iloc[0]["track_name"] == "Song A"
    assert df.iloc[0]["artist_name"] == "Artist A"
    assert df.iloc[0]["recording_mbid"] == "1234"
