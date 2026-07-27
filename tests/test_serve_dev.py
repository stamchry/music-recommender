import json
from unittest.mock import MagicMock, patch
from src.serve_dev import RecommenderDevServer

@patch("src.serve_dev.lambda_handler")
def test_recommender_dev_server_intercepts_api_recommend(mock_lambda):
    mock_lambda.return_value = {"statusCode": 200, "body": json.dumps({"status": "ok"})}
    
    # Mocking standard HTTP request handler attributes
    handler = RecommenderDevServer.__new__(RecommenderDevServer)
    handler.path = "/api/recommend?username=trampakulas"
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    
    handler.do_GET()
    
    mock_lambda.assert_called_once_with({"queryStringParameters": {"username": "trampakulas"}})
    handler.send_response.assert_called_once_with(200)
    handler.wfile.write.assert_called_once()
