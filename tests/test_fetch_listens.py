import pytest
from unittest.mock import patch, MagicMock
from src.fetch_listens import fetch_listens

@patch("src.fetch_listens.requests.get")
def test_fetch_listens_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "payload": {
            "listens": [
                {"listened_at": 1620000000, "track_metadata": {"track_name": "Test Track"}}
            ]
        }
    }
    mock_get.return_value = mock_response
    
    listens = fetch_listens("test_user", max_pages=1)
    
    assert len(listens) == 1
    assert listens[0]["track_metadata"]["track_name"] == "Test Track"
    mock_get.assert_called_once()
