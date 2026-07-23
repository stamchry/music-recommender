import os
import logging
import pickle
from pathlib import Path
import scipy.sparse as sparse
import pandas as pd
from dotenv import load_dotenv

os.environ["OPENBLAS_NUM_THREADS"] = "1"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_model(model_dir):
    with open(model_dir / "als_model.pkl", "rb") as f:
        model = pickle.load(f)
    with open(model_dir / "mappings.pkl", "rb") as f:
        mappings = pickle.load(f)
    return model, mappings

def recommend(username, model_dir, data_dir, n_recommendations=10):
    try:
        model, mappings = load_model(model_dir)
    except FileNotFoundError:
        logger.error("Model files not found. Run train_model.py first.")
        return
        
    user_cat = mappings['user_cat']
    artist_cat = mappings['artist_cat']
    
    if username not in user_cat:
        logger.error(f"User {username} not found in training data.")
        return
        
    user_id = user_cat.get_loc(username)
    
    input_file = data_dir / f"{username}_listens.parquet"
    if not input_file.exists():
        logger.error(f"Processed data file not found: {input_file}")
        return
        
    df = pd.read_parquet(input_file)
    df_counts = df.groupby(['user_name', 'artist_name']).size().reset_index(name='plays')
    
    df_counts = df_counts[df_counts['artist_name'].isin(artist_cat)]
    df_counts['artist_id'] = df_counts['artist_name'].apply(lambda x: artist_cat.get_loc(x))
    df_counts['user_id'] = user_id
    
    user_item_data = sparse.csr_matrix(
        (df_counts['plays'].astype(float), (df_counts['user_id'], df_counts['artist_id'])),
        shape=(len(user_cat), len(artist_cat))
    )
    
    logger.info(f"Generating top {n_recommendations} recommendations for {username}...")
    
    ids, scores = model.recommend(
        user_id, 
        user_item_data, 
        N=n_recommendations,
        filter_already_liked_items=True
    )
    
    print(f"\nTop {n_recommendations} Recommendations for {username}:")
    print("-" * 40)
    for i, (artist_id, score) in enumerate(zip(ids, scores)):
        artist_name = artist_cat[artist_id]
        print(f"{i+1}. {artist_name} (Score: {score:.4f})")
    print("-" * 40)

def main():
    load_dotenv()
    username = os.getenv("LISTENBRAINZ_USERNAME")
    
    if not username:
        logger.error("LISTENBRAINZ_USERNAME not found in environment.")
        return
        
    base_dir = Path(__file__).resolve().parent.parent
    model_dir = base_dir / "models"
    data_dir = base_dir / "data" / "processed"
    
    recommend(username, model_dir, data_dir)

if __name__ == "__main__":
    main()
