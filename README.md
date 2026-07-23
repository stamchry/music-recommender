# Music Recommender

A music recommendation engine using the ListenBrainz API, designed to run locally and eventually be deployed on AWS. 

This project aims to demonstrate building a complete data science pipeline:
1. Fetching data from an external REST API (ListenBrainz)
2. Cleaning and processing JSON data into a tabular Parquet format
3. Training an implicit-feedback Alternating Least Squares (ALS) model 
4. Serving recommendations based on the trained model

## Architecture
- **data/raw/**: Contains raw JSON data pulled from the API.
- **data/processed/**: Contains cleaned Parquet files ready for training.
- **models/**: Contains serialized ALS models and label encodings.
- **src/**: Python source code for data fetching, cleaning, training, and inference.
- **notebooks/**: Jupyter notebooks for EDA and experimentation.

## Setup Instructions

1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Copy `.env.example` to `.env` and fill in your details:
   ```bash
   cp .env.example .env
   ```
   Set `LISTENBRAINZ_USERNAME` to your ListenBrainz username.

## Usage

Run the pipeline steps in order:

1. **Fetch Data:**
   ```bash
   python src/fetch_listens.py
   ```
   
2. **Clean Data:**
   ```bash
   python src/clean_data.py
   ```
   
3. **Train Model:**
   ```bash
   python src/train_model.py
   ```

4. **Get Recommendations:**
   ```bash
   python src/recommend.py
   ```

## Testing

Run tests using pytest:
```bash
pytest tests/
```

## Results
*To be filled later with offline evaluation metrics (Precision@K, NDCG, etc.) and model performance details.*
