import json
import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch
from src import lambda_function

@pytest.fixture
def mock_cached_model():
    lambda_function.MODEL_CACHE.clear()
    mock_model = MagicMock()
    mock_model.item_factors = np.array([
        [1.0, 0.0], [0.5, 0.5], [0.1, 0.1]
    ])
    mock_model.recommend.return_value = ([0, 1], [0.95, 0.75])
    mappings = {
        "user_cat": pd.Index(["test_user"]),
        "artist_cat": pd.Index(["Daft Punk", "Kraftwerk", "Black Sabbath"])
    }
    lambda_function.MODEL_CACHE["model"] = mock_model
    lambda_function.MODEL_CACHE["mappings"] = mappings
    return mock_model, mappings

def test_autocomplete_endpoint(mock_cached_model):
    event = {"queryStringParameters": {"autocomplete": "daft"}}
    response = lambda_function.lambda_handler(event)
    assert response["statusCode"] == 200
    data = json.loads(response["body"])
    assert data["matches"] == ["Daft Punk"]

def test_predict_custom_mixer_negative_rating(mock_cached_model):
    event = {
        "queryStringParameters": {
            "artists": "Daft Punk:5,Black Sabbath:-5"
        }
    }
    response = lambda_function.lambda_handler(event)
    assert response["statusCode"] == 200
    data = json.loads(response["body"])
    assert data["profile_matches_found"] == 2
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0

def test_lambda_handler_post_json_body(mock_cached_model):
    event = {
        "body": json.dumps({
            "artists": [{"name": "Daft Punk", "rating": 5.0}]
        })
    }
    response = lambda_function.lambda_handler(event)
    assert response["statusCode"] == 200
    data = json.loads(response["body"])
    assert data["username"] == "Studio Custom Profile"

@patch("src.lambda_function.requests.get")
def test_fetch_user_artist_profile_404(mock_get, mock_cached_model):
    mock_get.return_value = MagicMock(status_code=404)
    res = lambda_function.lambda_handler({"queryStringParameters": {"username": "unknown_user"}})
    assert res["statusCode"] == 404
    assert "No listening history found" in json.loads(res["body"])["error"]

@patch("src.lambda_function.requests.get")
def test_fetch_user_artist_profile_success(mock_get, mock_cached_model):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "payload": {
            "artists": [
                {"artist_name": "Daft Punk", "listen_count": 42}
            ]
        }
    }
    mock_get.return_value = mock_resp
    res = lambda_function.lambda_handler({"queryStringParameters": {"username": "test_user"}})
    assert res["statusCode"] == 200
    data = json.loads(res["body"])
    assert data["username"] == "test_user"
    assert data["profile_matches_found"] == 1
