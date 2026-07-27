import pytest
import pandas as pd
from src.train_model import train_model

def test_train_model_success(tmp_path):
    df = pd.DataFrame({
        "user_name": ["user1", "user1", "user2", "user2", "user3"],
        "artist_name": ["Artist A", "Artist B", "Artist A", "Artist C", "Artist B"]
    })
    input_file = tmp_path / "all_listens.parquet"
    model_dir = tmp_path / "models"
    df.to_parquet(input_file)
    
    train_model(input_file, model_dir, factors=5, iterations=2)
    
    assert (model_dir / "als_model.pkl").exists()
    assert (model_dir / "mappings.pkl").exists()

def test_train_model_empty_data(tmp_path, caplog):
    df = pd.DataFrame(columns=["user_name", "artist_name"])
    input_file = tmp_path / "empty.parquet"
    model_dir = tmp_path / "models"
    df.to_parquet(input_file)
    
    train_model(input_file, model_dir)
    assert "No data available" in caplog.text
    assert not (model_dir / "als_model.pkl").exists()
