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

def train_model(input_file, model_dir):
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
        factors=50, 
        regularization=0.1, 
        iterations=20, 
        random_state=42
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
    load_dotenv()
    
    base_dir = Path(__file__).resolve().parent.parent
    input_file = base_dir / "data" / "processed" / "all_listens.parquet"
    model_dir = base_dir / "models"
    
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}. Run clean_data.py first.")
        return
        
    train_model(input_file, model_dir)

if __name__ == "__main__":
    main()
