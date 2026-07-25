import os
import sys
import ctypes

# Pre-load packaged OpenMP shared library (libgomp) when running inside AWS Lambda container
if os.path.exists("/var/task/lib/libgomp.so.1"):
    try:
        ctypes.CDLL("/var/task/lib/libgomp.so.1", mode=ctypes.RTLD_GLOBAL)
    except Exception as e:
        print(f"Notice: pre-loading libgomp encountered: {e}")

import json
import time
import pickle
import logging
from pathlib import Path
import requests
import numpy as np
import scipy.sparse as sparse
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Warm-RAM Cache: Keeps loaded models in memory across repeated Lambda invocations for <50ms response times
MODEL_CACHE = {}

def get_model_and_mappings():
    """
    Load serialized ALS model and mappings.
    Tries local disk first (for dev/testing), then falls back to downloading from AWS S3 (for Lambda production).
    """
    if 'model' in MODEL_CACHE and 'mappings' in MODEL_CACHE:
        return MODEL_CACHE['model'], MODEL_CACHE['mappings']
        
    base_dir = Path(__file__).resolve().parent.parent
    local_model = base_dir / "models" / "als_model.pkl"
    local_mappings = base_dir / "models" / "mappings.pkl"
    
    # Check local models directory first
    if local_model.exists() and local_mappings.exists():
        logger.info("Loading model artifacts from local disk...")
        with open(local_model, "rb") as f:
            model = pickle.load(f)
        with open(local_mappings, "rb") as f:
            mappings = pickle.load(f)
    else:
        # We are in AWS Lambda or cloud environment - download lightweight artifacts from S3 to /tmp
        logger.info("Local models not found. Fetching from AWS S3 into /tmp storage...")
        import boto3
        bucket_name = os.getenv("AWS_S3_BUCKET")
        if not bucket_name:
            raise RuntimeError("AWS_S3_BUCKET environment variable not configured and local models not found.")
            
        s3 = boto3.client("s3")
        tmp_model = "/tmp/als_model.pkl"
        tmp_mappings = "/tmp/mappings.pkl"
        
        s3.download_file(bucket_name, "models/als_model.pkl", tmp_model)
        s3.download_file(bucket_name, "models/mappings.pkl", tmp_mappings)
        
        with open(tmp_model, "rb") as f:
            model = pickle.load(f)
        with open(tmp_mappings, "rb") as f:
            mappings = pickle.load(f)
            
    # Cache in warm Lambda RAM
    MODEL_CACHE['model'] = model
    MODEL_CACHE['mappings'] = mappings
    return model, mappings

def fetch_user_artist_profile(username, max_artists=50):
    """
    Fetch pre-computed all-time top artist counts for a user from the ListenBrainz stats engine.
    Avoids single-album bias and completes in <200 milliseconds without massive log downloading.
    """
    url = f"https://api.listenbrainz.org/1/stats/user/{username}/artists"
    params = {"count": max_artists}
    logger.info(f"Querying live ListenBrainz profile stats for {username}...")
    
    response = requests.get(url, params=params, timeout=10)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    
    data = response.json()
    return data.get("payload", {}).get("artists", [])

def predict_recommendations(username, n_recommendations=10):
    """
    Perform on-the-fly Collaborative Filtering recommendation via Matrix Folding-In.
    Works seamlessly for both historically trained users and brand new web app visitors!
    """
    model, mappings = get_model_and_mappings()
    artist_cat = mappings['artist_cat']
    
    # 1. Pull user's top artist profile from ListenBrainz API
    user_artists = fetch_user_artist_profile(username, max_artists=50)
    if not user_artists:
        raise ValueError(f"No listening history found for user '{username}' on ListenBrainz.")
        
    # 2. Build frequency-weighted user interaction vector against our dynamic S3 item factor catalog
    plays = []
    indices = []
    matched_artists = []
    
    for item in user_artists:
        name = item.get("artist_name")
        count = item.get("listen_count", 1)
        if name in artist_cat:
            idx = artist_cat.get_loc(name)
            plays.append(float(count))
            indices.append(idx)
            matched_artists.append({"name": name, "plays": count})
            
    if not plays:
        raise ValueError(f"None of user '{username}'s artists matched our trained acoustic item matrix.")
        
    user_sparse = sparse.csr_matrix(
        (plays, ([0] * len(plays), indices)), 
        shape=(1, len(artist_cat))
    )
    
    # 3. Apply instantaneous ALS Matrix Folding-In (recalculate_user=True)
    logger.info(f"Computing linear algebra matrix folding-in projection across {len(artist_cat):,} artist factors...")
    ids, scores = model.recommend(
        0,  # Temporary virtual user ID for projection
        user_sparse,
        N=n_recommendations,
        recalculate_user=True,
        filter_already_liked_items=True
    )
    
    recommendations = []
    for i, (artist_idx, score) in enumerate(zip(ids, scores)):
        recommendations.append({
            "rank": i + 1,
            "artist": artist_cat[artist_idx],
            "confidence": round(float(score), 4)
        })
        
    return {
        "username": username,
        "total_catalog_artists": len(artist_cat),
        "total_community_users": len(mappings.get("user_cat", [])),
        "profile_matches_found": len(matched_artists),
        "top_scrobbles_sampled": matched_artists[:5],
        "recommendations": recommendations
    }

def lambda_handler(event, context=None):
    """
    AWS Lambda entry point for serverless real-time inference over HTTP API Gateway or Function URLs.
    """
    load_dotenv(override=True)
    
    # Parse query parameter from GET request or fallback to test username
    params = event.get("queryStringParameters", {}) or {}
    username = params.get("username") or os.getenv("LISTENBRAINZ_USERNAME", "trampakulas")
    
    start_time = time.time()
    try:
        results = predict_recommendations(username, n_recommendations=10)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        results["execution_time_ms"] = elapsed_ms
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(results, ensure_ascii=False, indent=2)
        }
    except ValueError as ve:
        logger.warning(f"Inference warning for {username}: {ve}")
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(ve), "username": username})
        }
    except Exception as e:
        logger.exception("Unexpected error during cloud recommendation inference.")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error during recommendation projection."})
        }

if __name__ == "__main__":
    # Local developer simulator for rapid verification!
    print("Testing AWS Lambda HTTP event simulation locally...")
    mock_event = {"queryStringParameters": {"username": "trampakulas"}}
    response = lambda_handler(mock_event)
    print("\n--- MOCK HTTP RESPONSE FROM LAMBDA ---")
    print(f"Status Code: {response['statusCode']}")
    print("Body:")
    print(response['body'])
