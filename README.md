# Music Recommender System

An end-to-end music recommendation engine built with Python, DuckDB, and Alternating Least Squares (ALS) matrix factorization. Using real-world listening history from [ListenBrainz](https://listenbrainz.org/), this project covers the full pipeline: API collection, bulk data cleaning, SQL deduplication, model training, and generation of personalized artist recommendations.

Designed to run locally while easily syncing lightweight processed data to an AWS S3 free-tier bucket.

---

## How It Works

### 1. Hybrid Data Gathering
To build a realistic recommendation matrix without hitting API rate limits, the project gathers data from two sources:
* **Targeted API Fetches ([fetch_listens.py](file:///home/stamatis/projects/music-recommender/src/fetch_listens.py)):** Pulls the recent listening history for specific test users directly via the ListenBrainz REST API.
* **Bulk Daily Dumps ([fetch_dump.py](file:///home/stamatis/projects/music-recommender/src/fetch_dump.py)):** Downloads and decodes compressed daily data archives (`.tar.zst`), providing a dataset of over 4.5 million community listening events (~3.1 GB uncompressed) to teach the algorithm musical similarity.

### 2. Data Cleaning & Deduplication with DuckDB
Loading 3+ GB of nested JSON directly into Python memory with Pandas can cause performance bottlenecks. Instead, this project uses [clean_duckdb.py](file:///home/stamatis/projects/music-recommender/src/clean_duckdb.py) to run SQL queries straight over the raw files on disk:
* **Entity Resolution:** Normalizes inconsistent casing, double spaces, and strips out clutter tags from track names (like *"2011 Remaster"*, *"[Live]"*, or *"Bonus Track"*) to group duplicate songs together.
* **Noise Reduction:** Filters out obscure scrobbles, typo artist names, and bots by retaining active users ($\ge 10$ plays) and artists played $\ge 5$ times across the global community.
* **Result:** Transforms 4.5+ million JSON records into a single clean, fast-to-read ~48 MB Parquet file (`all_listens.parquet`) in about 20 seconds.

### 3. Collaborative Filtering Recommender
* Uses implicit feedback **Alternating Least Squares (ALS)** ([train_model.py](file:///home/stamatis/projects/music-recommender/src/train_model.py)) across an interaction matrix of ~15,000 users and ~62,000 artists.
* When predicting for a user ([recommend.py](file:///home/stamatis/projects/music-recommender/src/recommend.py)), it matches their acoustic taste profile against community clusters and recommends relevant artists that the user has not listened to yet.

### 4. Zero-Cost Cloud Storage (AWS S3)
* The heavy 3.1 GB raw JSON dump stays strictly on local storage and is git-ignored. 
* Only the 48 MB cleaned Parquet dataset and model weights (`als_model.pkl`, `mappings.pkl`) are synced to your AWS S3 bucket using [s3_utils.py](file:///home/stamatis/projects/music-recommender/src/s3_utils.py), consuming under 1% of the AWS Free Tier.

---

## Repository Structure

```text
├── data/
│   ├── raw/               # API JSON profiles & raw archive dumps (ignored by git)
│   └── processed/         # Cleaned output table (all_listens.parquet)
├── models/                # Saved ALS model files and categorical ID mappings
├── notebooks/             # Jupyter notebooks for testing model accuracy and loss convergence
├── src/
│   ├── fetch_listens.py   # REST API script for pulling explicit user histories
│   ├── fetch_dump.py      # Script for downloading daily ListenBrainz archives
│   ├── clean_duckdb.py    # DuckDB SQL cleaning, deduplication, and Parquet export
│   ├── train_model.py     # Script to train the ALS collaborative filtering model
│   ├── recommend.py       # Recommends top-10 discovery artists for a user
│   └── s3_utils.py        # Boto3 helpers for downloading/uploading model artifacts to S3
├── tests/                 # Unit tests
└── requirements.txt       # Dependencies (duckdb, implicit, pyarrow, boto3, etc.)
```

---

## Quick Start & Usage

1. **Clone the project and create a virtual environment:**
   ```bash
   git clone https://github.com/stamchry/music-recommender.git
   cd music-recommender
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Copy the example environment file and fill in your details:
   ```bash
   cp .env.example .env
   ```
   * `LISTENBRAINZ_USERNAME`: The primary user to generate recommendations for.
   * `LISTENBRAINZ_USERNAMES`: Comma-separated list of target accounts to harvest via API.
   * `AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: *(Optional)* For syncing processed data and models to AWS.

### Running the Full Pipeline

Execute the pipeline scripts in sequential order:

```bash
# 1. Fetch targeted user profiles via REST API
python src/fetch_listens.py

# 2. Download and unpack a daily ListenBrainz data dump (~3.1 GB)
python src/fetch_dump.py

# 3. Clean, deduplicate, and compile everything into a Parquet table with DuckDB
python src/clean_duckdb.py

# 4. Train the ALS collaborative filtering matrix
python src/train_model.py

# 5. Get your customized Top-10 artist recommendations
python src/recommend.py
```


---

## A Note on Production Deployment

In a real-world production setup, retraining a matrix factorization model from scratch every time a user visits a website is impractical and slow. This pipeline is built to cleanly fit into a standard **Two-Tier Architecture**:

1. **Offline Batch Processing (Nightly):** A scheduled script runs `clean_duckdb.py` and `train_model.py` across millions of records once a day, uploading the updated artist embedding vectors to an AWS S3 bucket.
2. **Real-Time Online Inference (On Demand):** When a user requests recommendations on a web application, an AWS Lambda function simply fetches their 10–20 most recent plays via API and applies matrix *"folding-in"* (a simple linear algebra projection against the fixed S3 item factors) to compute their custom recommendations in under 200 milliseconds without a database rebuild.
