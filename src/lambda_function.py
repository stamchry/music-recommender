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

def search_artist_catalog(query_prefix, limit=10):
    """
    Fast case-insensitive prefix and substring search across our warm RAM S3 artist dictionary.
    Sorted by latent embedding vector norm (popularity/interaction frequency) so famous artists pop up first!
    """
    model, mappings = get_model_and_mappings()
    artist_cat = mappings['artist_cat']
    query_clean = query_prefix.strip().lower()
    if not query_clean:
        return []
        
    candidate_indices = []
    for idx, name in enumerate(artist_cat):
        name_str = str(name).lower()
        if name_str.startswith(query_clean) or (len(query_clean) >= 3 and query_clean in name_str):
            candidate_indices.append(idx)
            if len(candidate_indices) >= 200:
                break
                
    # Sort matches by the L2 norm of their latent embedding factor (directly proportional to dataset popularity!)
    if candidate_indices and hasattr(model, "item_factors"):
        candidate_indices.sort(key=lambda idx: float(np.linalg.norm(model.item_factors[idx])), reverse=True)
        
    return [str(artist_cat[idx]) for idx in candidate_indices[:limit]]

def predict_recommendations(username=None, custom_artists=None, n_recommendations=10):
    """
    Perform on-the-fly Collaborative Filtering recommendation via Matrix Folding-In.
    Supports traditional ListenBrainz profiles OR real-time custom studio mixer artist profiles with +/- ratings!
    """
    model, mappings = get_model_and_mappings()
    artist_cat = mappings['artist_cat']
    
    plays = []
    indices = []
    matched_artists = []
    
    negative_indices = []
    negative_weights = []
    
    # Mode A: Interactive Custom Artist Profile (with positive/negative ratings)
    if custom_artists:
        display_name = username or "Studio Custom Profile"
        for item in custom_artists:
            name = item.get("name", item.get("artist_name"))
            rating = float(item.get("rating", item.get("weight", 5.0)))
            if name in artist_cat:
                idx = artist_cat.get_loc(name)
                if rating >= 0:
                    plays.append(float(rating))
                    indices.append(idx)
                    matched_artists.append({"name": name, "plays": int(rating), "rating_type": "positive"})
                else:
                    negative_indices.append(idx)
                    negative_weights.append(float(rating))
                    matched_artists.append({"name": name, "plays": int(rating), "rating_type": "negative"})
            else:
                logger.warning(f"Custom artist '{name}' not found in trained acoustic dictionary.")
    # Mode B: Classic ListenBrainz REST API profile fetch
    else:
        display_name = username or os.getenv("LISTENBRAINZ_USERNAME", "trampakulas")
        user_artists = fetch_user_artist_profile(display_name, max_artists=50)
        if not user_artists:
            raise ValueError(f"No listening history found for user '{display_name}' on ListenBrainz.")
        for item in user_artists:
            name = item.get("artist_name")
            count = item.get("listen_count", 1)
            if name in artist_cat:
                idx = artist_cat.get_loc(name)
                plays.append(float(count))
                indices.append(idx)
                matched_artists.append({"name": name, "plays": count, "rating_type": "positive"})
                
    if not plays:
        raise ValueError("No matching positively liked artists found to build recommendation vector.")
        
    user_sparse = sparse.csr_matrix(
        (plays, ([0] * len(plays), indices)), 
        shape=(1, len(artist_cat))
    )
    
    # 3. Apply instantaneous ALS Matrix Folding-In (recalculate_user=True)
    # If negative feedback exists, fetch an expanded candidate pool for similarity damping
    fetch_n = max(n_recommendations * 5, 50) if negative_indices else n_recommendations
    logger.info(f"Computing linear algebra matrix folding-in projection across {len(artist_cat):,} artist factors...")
    
    ids, scores = model.recommend(
        0,  # Temporary virtual user ID for projection (read-only against global matrix)
        user_sparse,
        N=fetch_n,
        recalculate_user=True,
        filter_already_liked_items=True
    )
    
    # 4. Apply vector cosine distance damping for negatively rated artists!
    if negative_indices and len(ids) > 0:
        item_factors = model.item_factors
        cand_list = list(zip(ids, scores))
        adjusted = []
        for cand_idx, score in cand_list:
            if cand_idx in negative_indices or cand_idx in indices:
                continue  # Skip any explicitly added artists
            cand_vec = item_factors[cand_idx]
            norm_c = np.linalg.norm(cand_vec) + 1e-9
            
            total_penalty = 0.0
            for neg_idx, neg_weight in zip(negative_indices, negative_weights):
                neg_vec = item_factors[neg_idx]
                norm_n = np.linalg.norm(neg_vec) + 1e-9
                cosine_sim = np.dot(cand_vec, neg_vec) / (norm_c * norm_n)
                if cosine_sim > 0:
                    total_penalty += abs(neg_weight) * float(cosine_sim) * 0.35
                    
            adjusted.append((cand_idx, float(score - total_penalty)))
        adjusted.sort(key=lambda x: x[1], reverse=True)
        ids = [x[0] for x in adjusted[:n_recommendations]]
        scores = [x[1] for x in adjusted[:n_recommendations]]
    else:
        ids = ids[:n_recommendations]
        scores = scores[:n_recommendations]
    
    recommendations = []
    for i, (artist_idx, score) in enumerate(zip(ids, scores)):
        recommendations.append({
            "rank": i + 1,
            "artist": str(artist_cat[artist_idx]),
            "confidence": round(float(score), 4)
        })
        
    return {
        "username": display_name,
        "total_catalog_artists": len(artist_cat),
        "total_community_users": len(mappings.get("user_cat", [])),
        "profile_matches_found": len(matched_artists),
        "top_scrobbles_sampled": matched_artists[:10],
        "recommendations": recommendations
    }

def lambda_handler(event, context=None):
    """
    AWS Lambda entry point for serverless real-time inference over HTTP API Gateway or Function URLs.
    Supports autocomplete queries, custom artist rating mixers, and classic ListenBrainz accounts.
    """
    load_dotenv(override=True)
    params = event.get("queryStringParameters", {}) or {}
    
    # Handle Real-Time Catalog Autocomplete Request
    if "autocomplete" in params:
        query_text = params.get("autocomplete", "").strip()
        matches = search_artist_catalog(query_text, limit=10)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"query": query_text, "matches": matches}, ensure_ascii=False)
        }
        
    start_time = time.time()
    try:
        custom_artists = None
        username = params.get("username")
        
        # Parse JSON POST body if submitted by Studio Mixer
        if event.get("body"):
            try:
                body_data = json.loads(event["body"])
                if isinstance(body_data, dict):
                    if "autocomplete" in body_data:
                        matches = search_artist_catalog(body_data["autocomplete"], limit=10)
                        return {
                            "statusCode": 200,
                            "headers": {"Content-Type": "application/json"},
                            "body": json.dumps({"query": body_data["autocomplete"], "matches": matches}, ensure_ascii=False)
                        }
                    if "artists" in body_data:
                        custom_artists = body_data["artists"]
                    if "username" in body_data and not username:
                        username = body_data["username"]
            except Exception as parse_err:
                logger.warning(f"Could not parse JSON POST body: {parse_err}")

        # Parse GET parameter ?artists=Daft Punk:5,Kraftwerk:3,Black Sabbath:-5
        if not custom_artists and params.get("artists"):
            artists_raw = params.get("artists")
            custom_artists = []
            for part in artists_raw.split(","):
                part_clean = part.strip()
                if not part_clean:
                    continue
                if ":" in part_clean:
                    pieces = part_clean.rsplit(":", 1)
                    try:
                        custom_artists.append({"name": pieces[0].strip(), "rating": float(pieces[1])})
                    except ValueError:
                        custom_artists.append({"name": pieces[0].strip(), "rating": 5.0})
                else:
                    custom_artists.append({"name": part_clean, "rating": 5.0})

        if not custom_artists and not username:
            username = os.getenv("LISTENBRAINZ_USERNAME", "trampakulas")

        results = predict_recommendations(username=username, custom_artists=custom_artists, n_recommendations=10)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        results["execution_time_ms"] = elapsed_ms
        
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(results, ensure_ascii=False, indent=2)
        }
    except ValueError as ve:
        logger.warning(f"Inference warning: {ve}")
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(ve), "username": str(username or 'Custom Mixer')})
        }
    except Exception as e:
        logger.exception("Unexpected error during cloud recommendation inference.")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error during recommendation projection."})
        }

if __name__ == "__main__":
    # Local developer simulation for rapid verification!
    print("--- 1. TESTING AUTOCOMPLETE ENDPOINT LOCALLY ---")
    mock_auto = {"queryStringParameters": {"autocomplete": "mic"}}
    auto_res = lambda_handler(mock_auto)
    print("Autocomplete response:", auto_res["body"])
    
    print("\n--- 2. TESTING CUSTOM STUDIO MIXER WITH POSITIVE/NEGATIVE RATINGS ---")
    mock_custom = {"queryStringParameters": {"artists": "Michael Jackson:5,Elvis Presley:4,Black Sabbath:-5"}}
    custom_res = lambda_handler(mock_custom)
    print("Custom Recommendations status:", custom_res["statusCode"])
    print("Body:", custom_res["body"])
