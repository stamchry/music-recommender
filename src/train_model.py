import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import logging
import pickle
from pathlib import Path
import pandas as pd
import scipy.sparse as sparse
import implicit
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def train_model(input_file, model_dir, factors=50, regularization=0.1, iterations=20, random_state=42):
    logger.info(f"Loading data from {input_file}")
    df = pd.read_parquet(input_file)
    
    if len(df) == 0:
        logger.error("No data available to train the model.")
        return
        
    # We will build an implicit feedback model where items are artists.
    df_counts = df.groupby(['user_name', 'artist_name']).size().reset_index(name='plays')
    
    users = df_counts['user_name'].astype('category')
    artists = df_counts['artist_name'].astype('category')
    
    user_ids = users.cat.codes
    artist_ids = artists.cat.codes
    
    df_counts['user_id'] = user_ids
    df_counts['artist_id'] = artist_ids
    
    # Create sparse matrix: rows=users, cols=artists, values=plays
    # implicit >= 0.5.0 expects a user-item matrix for training
    user_item_data = sparse.csr_matrix(
        (df_counts['plays'].astype(float), (df_counts['user_id'], df_counts['artist_id']))
    )
    
    logger.info(f"Training model with {len(users.cat.categories)} users and {len(artists.cat.categories)} items.")
    
    # Initialize ALS model
    model = implicit.als.AlternatingLeastSquares(
        factors=factors, 
        regularization=regularization, 
        iterations=iterations, 
        random_state=random_state
    )
    
    model.fit(user_item_data)
    
    # Save mappings and model
    model_dir.mkdir(parents=True, exist_ok=True)
    
    mappings = {
        'user_cat': users.cat.categories,
        'artist_cat': artists.cat.categories
    }
    with open(model_dir / "mappings.pkl", "wb") as f:
        pickle.dump(mappings, f)
        
    with open(model_dir / "als_model.pkl", "wb") as f:
        pickle.dump(model, f)
        
    logger.info("Model training complete and saved.")

def main():
    load_dotenv(override=True)
    from src.config import ALL_LISTENS_PARQUET, MODELS_DIR, ALS_FACTORS, ALS_REGULARIZATION, ALS_ITERATIONS, ALS_RANDOM_STATE
    
    input_file = ALL_LISTENS_PARQUET
    model_dir = MODELS_DIR
    
    bucket = os.getenv("AWS_S3_BUCKET")
    if bucket:
        from src.s3_utils import download_file, upload_directory
        download_file(bucket, "data/processed/all_listens.parquet", input_file)
    
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}. Run clean_duckdb.py first.")
        return
        
    train_model(input_file, model_dir, factors=ALS_FACTORS, regularization=ALS_REGULARIZATION, iterations=ALS_ITERATIONS, random_state=ALS_RANDOM_STATE)
    
    if bucket:
        from src.s3_utils import upload_directory
        upload_directory(model_dir, bucket, "models")

if __name__ == "__main__":
    main()
