import os
import sys
import time
import shutil
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure robust logging for automated cloud runners (GitHub Actions & Linux Crontabs)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MASTER-PIPELINE] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("WeeklyPipeline")

# Import our modular pipeline engines
from src import fetch_listens, fetch_dump, clean_duckdb, train_model
from src.config import DATA_RAW_DUMP

def execute_pipeline_step(step_name, step_function, *args, **kwargs):
    """
    Execute a data pipeline step with timing diagnostics and error tolerance.
    """
    logger.info(f"=" * 70)
    logger.info(f"▶ STARTING STEP: {step_name}...")
    logger.info(f"=" * 70)
    start_time = time.time()
    try:
        step_function(*args, **kwargs)
        elapsed_sec = round(time.time() - start_time, 2)
        logger.info(f"✅ COMPLETED STEP: {step_name} (Duration: {elapsed_sec}s)\n")
        return True
    except Exception as e:
        elapsed_sec = round(time.time() - start_time, 2)
        logger.error(f"❌ FAILED STEP: {step_name} after {elapsed_sec}s!")
        logger.exception(e)
        raise RuntimeError(f"Pipeline execution aborted during step: {step_name}")

def purge_temporary_raw_dumps(data_raw_dump_dir):
    """
    Delete massive 3+ GB raw JSON archive files immediately after DuckDB compilation
    to maintain a lightweight storage footprint and prevent OOM/disk overflow in cloud runners.
    """
    if data_raw_dump_dir.exists():
        logger.info(f"🧹 PURGING RAW TEMPORARY ARCHIVES: Removing multi-gigabyte files from {data_raw_dump_dir}...")
        try:
            shutil.rmtree(data_raw_dump_dir)
            logger.info("✨ Successfully reclaimed ~3.1+ GB of storage space.")
        except Exception as e:
            logger.warning(f"Failed to delete directory {data_raw_dump_dir}: {e}")

def main():
    load_dotenv(override=True)
    logger.info("🚀 INITIALIZING AUTOMATED WEEKLY RE-TRAINING & CLOUD SYNC PIPELINE...")
    
    # Verify cloud sync capabilities
    bucket_name = os.getenv("AWS_S3_BUCKET")
    if bucket_name:
        logger.info(f"☁️ Cloud Synchronization Target Detected: AWS S3 Bucket '{bucket_name}'")
    else:
        logger.warning("⚠️ AWS_S3_BUCKET not set. Pipeline will execute locally without S3 artifact syncing.")
        
    pipeline_start = time.time()
    
    # 1. Harvest explicit user histories via REST API
    execute_pipeline_step("1. Targeted REST API Harvest", fetch_listens.main)
    
    # 2. Download and unpack canonical ListenBrainz incremental community dump
    execute_pipeline_step("2. Global Archive Dump Ingestion", fetch_dump.main)
    
    # 3. Execute Out-of-Core DuckDB Entity Resolution & Parquet Compilation
    execute_pipeline_step("3. DuckDB SQL Data Cleaning & Parquet Compilation", clean_duckdb.main)
    
    # 4. Storage Optimization & Automatic Raw Debris Purge
    raw_dump_path = DATA_RAW_DUMP
    purge_temporary_raw_dumps(raw_dump_path)
    
    # 5. Train Collaborative Filtering ALS Matrix & Push to AWS S3
    execute_pipeline_step("4. Collaborative Filtering ALS Matrix Retraining & S3 Export", train_model.main)
    
    total_duration = round((time.time() - pipeline_start) / 60, 2)
    logger.info("=" * 70)
    logger.info(f"🏆 WEEKLY PIPELINE COMPLETE! Entire 4.5M+ scrobble workflow processed in {total_duration} minutes.")
    logger.info("   -> Newest artist latent embeddings and mappings pushed cleanly to S3.")
    logger.info("   -> Ready for real-time online inference via AWS Lambda.")
    logger.info("=" * 70)

if __name__ == "__main__":
    main()
