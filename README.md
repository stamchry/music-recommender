# 🎧 Serverless Music Recommender Engine & Live Studio Console

[![Live Web Studio Demo](https://img.shields.io/badge/Live%20Demo-Studio%20Console-00D95A?style=for-the-badge&logo=githubpages&logoColor=white)](https://stamchry.github.io/music-recommender/)
[![AWS Serverless Backend](https://img.shields.io/badge/AWS%20Lambda-Serverless%20ML-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white)](https://aws.amazon.com/lambda/)
[![DuckDB Engine](https://img.shields.io/badge/DuckDB-Out--of--Core%20ETL-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![Automated Retraining CI/CD](https://img.shields.io/badge/GitHub%20Actions-Automated%20MLOps-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/stamchry/music-recommender/actions)

An automated, end-to-end cloud music discovery platform powered by **DuckDB**, **Alternating Least Squares (ALS)** collaborative filtering, and **AWS Lambda**. Engineered from the ground up for zero server maintenance and running completely within a **$0.00 infrastructure operations footprint**.

Experience the interactive web demo live at: **[stamchry.github.io/music-recommender](https://stamchry.github.io/music-recommender/)** 🚀

---

## 🏛️ Two-Tier Serverless MLOps Architecture

This platform solves traditional machine learning infrastructure scale constraints by cleanly decoupling computational offline training from real-time online inference:

```text
 ┌───────────────────────────────────────────────────────────┐
 │        TIER 1: OFFLINE MLOPS BATCH PIPELINE               │
 │        (Automated Weekly via GitHub Actions)               │
 └───────────────────────────────────────────────────────────┘
         │
         ├── 1. Ingest ~3.1 GB Compressed ListenBrainz Archives
         ├── 2. DuckDB SQL Out-of-Core Normalization & Deduplication
         ├── 3. ALS Matrix Factorization Training (~62k Artists)
         └── 4. Sync Serialized Model Weights directly to AWS S3
                 │
                 ▼
          ┌─────────────┐
          │   AWS S3    │  <── Low-cost Model & Parquet Staging
          └─────────────┘
                 │
 ┌───────────────┼───────────────────────────────────────────┐
 │               ▼                                           │
 │     AWS LAMBDA INFERENCE ENDPOINT (Serverless API)        │
 │     • Warm-RAM Model Caching (<50ms execution speed)     │
 │     • On-the-Fly Matrix Folding-in Projection             │
 └───────────────────────────────────────────────────────────┘
                 ▲
                 │  REST API (JSON)
                 ▼
 ┌───────────────────────────────────────────────────────────┐
 │      STUDIO CONSOLE INTERFACE (Hosted via GitHub Pages)   │
 │      • Terminal Monitor Aesthetics & Acoustic Match Logs  │
 │      • Instant Streaming Links (Spotify & YouTube Music) │
 └───────────────────────────────────────────────────────────┘
```

---

## ✨ Core Highlights & Engineering Accomplishments

### 1. Out-of-Core ETL with DuckDB
Loading over **4.5 million nested community listen events (~3.1 GB)** directly into RAM with Pandas routinely causes out-of-memory bottlenecks. This engine utilizes [clean_duckdb.py](file:///home/stamatis/projects/music-recommender/src/clean_duckdb.py) to perform high-speed SQL analytics straight across raw disk archives:
* **Advanced Entity Resolution:** Normalizes inconsistent casing, double spaces, and strips intrusive audio tags (*"2011 Remaster"*, *"[Live]"*, *"Bonus Track"*) to unify artist vectors.
* **Intelligent Noise Filtering:** Eliminates spam bots and single-play anomalies by isolating active community listening patterns ($\ge 10$ user plays, $\ge 5$ artist community impressions).
* **Storage Footprint:** Condenses 3.1 GB of uncompressed JSON into an optimized **~48 MB Parquet file** in under 20 seconds.

### 2. High-Speed Collaborative Filtering Engine
* Employs implicit feedback **Alternating Least Squares (ALS)** ([train_model.py](file:///home/stamatis/projects/music-recommender/src/train_model.py)) across an active interaction matrix of **~15,000 users** and **~62,900 distinct artists**.
* Implements mathematical matrix *"folding-in"* ([lambda_function.py](file:///home/stamatis/projects/music-recommender/src/lambda_function.py)), projecting a user's recent real-time listening history directly against fixed S3 artist embeddings to generate fresh taste discoveries instantly without requiring database retraining.

### 3. Fully Automated Cloud CI/CD Pipeline
* **Automated Retraining:** Every Sunday at 02:00 UTC (or on demand), an automated [GitHub Actions Pipeline](file:///home/stamatis/projects/music-recommender/.github/workflows/weekly_retrain.yml) activates, downloads fresh public dataset dumps, retrains the ALS latent factor arrays, and syncs newly minted model binaries directly to AWS S3.
* **Serverless Edge Inference:** AWS Lambda serves instant HTTP recommendations using custom bundled native openMP binary dependencies (`libgomp.so`), staying within AWS's generous $0.00 Free Tier.
* **Global Edge Hosting:** The Studio Console web interface ([web/](file:///home/stamatis/projects/music-recommender/web/index.html)) is deployed continuous-release to **GitHub Pages**, providing global accessibility with free custom SSL encryption.

---

## 📁 Repository Directory Structure

```text
├── .github/
│   └── workflows/
│       ├── weekly_retrain.yml   # Automated scheduled model retraining & AWS S3 synchronization
│       ├── deploy_lambda.yml    # CI/CD packaging pipeline for Serverless AWS Lambda API
│       └── pages.yml            # Automated global web console hosting via GitHub Pages
├── deploy/
│   └── lambda_requirements.txt  # Lightweight production runtime pins optimized for Amazon Linux 2
├── src/
│   ├── lambda_function.py       # Cloud serverless inference API handler with RAM model caching
│   ├── clean_duckdb.py          # Out-of-core SQL entity deduplication and Parquet compilation
│   ├── train_model.py           # ALS collaborative filtering training loop & model serializer
│   ├── recommend.py             # Local CLI recommendation evaluation script
│   ├── fetch_listens.py         # ListenBrainz REST API scraper for specific test profiles
│   ├── fetch_dump.py            # Compressed archive grabber (.tar.zst) for daily datasets
│   └── s3_utils.py              # AWS S3 cloud persistence utilities
├── web/
│   ├── index.html               # Studio Web Console layout & acoustic interactive controller
│   ├── style.css                # Terminal aesthetic styling, neon accents & LED animations
│   └── app.js                   # JavaScript API fetcher with real-time diagnostic console logs
├── requirements.txt             # Primary project & analytical notebook dependencies
└── README.md                    # Engineering architecture guide
```

---

## ⚡ Quick Start & Local Exploration

Want to experiment with the recommendation math locally on your personal machine?

1. **Clone the repository and spin up a virtual environment:**
   ```bash
   git clone https://github.com/stamchry/music-recommender.git
   cd music-recommender
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install core project dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Parameters:**
   Copy the provided configuration template and add your desired test targets:
   ```bash
   cp .env.example .env
   ```
   * `LISTENBRAINZ_USERNAME`: Account name to run CLI discovery evaluations against.
   * `AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: *(Optional)* Required only if testing S3 remote synchronization locally.

### Executing the Local Data & ML Pipeline

Run the modular scripts sequentially to train your custom recommendation weights from scratch:

```bash
# 1. Pull specific target user profiles via ListenBrainz REST API
python src/fetch_listens.py

# 2. Download and decompress public daily community dataset archive (~3.1 GB)
python src/fetch_dump.py

# 3. Clean, normalize, and compile dataset into Parquet table using DuckDB SQL
python src/clean_duckdb.py

# 4. Train Collaborative Filtering latent factor matrix arrays
python src/train_model.py

# 5. Execute offline Top-10 recommendation inference via CLI
python src/recommend.py
```

### Testing the Cloud Lambda API Handler Locally
You can simulate an authentic AWS HTTP event invocation directly on your laptop:
```bash
python src/lambda_function.py
```
This prints out the exact JSON API payload identical to what is served across the cloud edge! 🎧
