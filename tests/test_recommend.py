import pickle
import pytest
import pandas as pd
import numpy as np
from src.recommend import load_model, recommend

class DummyModel:
    def recommend(self, user_id, user_items, N=10, filter_already_liked_items=True, recalculate_user=False):
        return (np.array([1, 2]), np.array([0.9, 0.8]))

def test_recommend(tmp_path, capsys):
    model_dir = tmp_path / "models"
    data_dir = tmp_path / "data"
    model_dir.mkdir()
    data_dir.mkdir()
    
    # Mock mappings & model
    mappings = {
        "user_cat": pd.Index(["test_user"]),
        "artist_cat": pd.Index(["Artist A", "Artist B", "Artist C"])
    }
    with open(model_dir / "mappings.pkl", "wb") as f:
        pickle.dump(mappings, f)
        
    mock_model = DummyModel()
    with open(model_dir / "als_model.pkl", "wb") as f:
        pickle.dump(mock_model, f)
        
    # Mock data
    df = pd.DataFrame({
        "user_name": ["test_user", "test_user"],
        "artist_name": ["Artist A", "Artist A"]
    })
    df.to_parquet(data_dir / "all_listens.parquet")
    
    recommend("test_user", model_dir, data_dir, n_recommendations=2)
    out = capsys.readouterr().out
    assert "Top 2 Recommendations for test_user" in out
    assert "Artist B (Score: 0.9000)" in out

def test_recommend_missing_model_files(tmp_path, caplog):
    model_dir = tmp_path / "non_existent_model_dir"
    data_dir = tmp_path / "data"
    recommend("test_user", model_dir, data_dir)
    assert "Model files not found" in caplog.text

def test_recommend_user_not_in_data(tmp_path, caplog):
    model_dir = tmp_path / "models"
    data_dir = tmp_path / "data"
    model_dir.mkdir()
    
    mappings = {
        "user_cat": pd.Index(["known_user"]),
        "artist_cat": pd.Index(["Artist A"])
    }
    with open(model_dir / "mappings.pkl", "wb") as f:
        pickle.dump(mappings, f)
    with open(model_dir / "als_model.pkl", "wb") as f:
        pickle.dump(DummyModel(), f)
        
    recommend("unknown_user", model_dir, data_dir)
    assert "not found in training data" in caplog.text
