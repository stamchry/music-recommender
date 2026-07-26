"""Centralized project paths and configuration constants."""

import os
from pathlib import Path

# Project root directory (two levels up from this file if in src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
DATA_RAW = DATA_DIR / "raw"
DATA_PROCESSED = DATA_DIR / "processed"
DATA_RAW_DUMP = DATA_RAW / "dump"

# Model directory
MODELS_DIR = PROJECT_ROOT / "models"

# Web directory
WEB_DIR = PROJECT_ROOT / "web"

# Default file paths
ALL_LISTENS_PARQUET = DATA_PROCESSED / "all_listens.parquet"
ALS_MODEL_FILE = MODELS_DIR / "als_model.pkl"
MAPPINGS_FILE = MODELS_DIR / "mappings.pkl"

# Model hyperparameters (overridable via environment variables)
ALS_FACTORS = int(os.getenv("ALS_FACTORS", "50"))
ALS_REGULARIZATION = float(os.getenv("ALS_REGULARIZATION", "0.1"))
ALS_ITERATIONS = int(os.getenv("ALS_ITERATIONS", "20"))
ALS_RANDOM_STATE = int(os.getenv("ALS_RANDOM_STATE", "42"))

# Feature selection thresholds
MIN_USER_PLAYS = int(os.getenv("MIN_USER_PLAYS", "10"))
MIN_ARTIST_PLAYS = int(os.getenv("MIN_ARTIST_PLAYS", "5"))

# Ingestion pipeline rolling window duration (in days/dumps)
FETCH_NUM_DAYS = int(os.getenv("FETCH_NUM_DAYS", "7"))

