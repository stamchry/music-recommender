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

def run_iterative_ingestion_and_cleaning():
    """
    Execute a low-memory iterative rolling-window ingestion and DuckDB cleaning loop.
    Downloads one daily community archive at a time, stages cleaned entities into DuckDB,
    and immediately purges the raw multi-gigabyte debris before downloading the next day.
    """
    from src.config import DATA_RAW_DUMP, DATA_RAW, DATA_PROCESSED, ALL_LISTENS_PARQUET, MIN_USER_PLAYS, MIN_ARTIST_PLAYS, FETCH_NUM_DAYS
    from src import fetch_dump, clean_duckdb
    
    staging_db_path = DATA_PROCESSED / "staging_listens.duckdb"
    if staging_db_path.exists():
        logger.info(f"Removing existing staging database at {staging_db_path} for clean run...")
        try:
            staging_db_path.unlink()
        except Exception:
            pass
        
    # 1. Ingest any targeted REST API user history files first
    api_files = list(DATA_RAW.glob("*_listens.json"))
    if api_files:
        logger.info(f"Staging {len(api_files)} targeted REST API profiles into DuckDB...")
        clean_duckdb.ingest_into_staging_db([str(f) for f in api_files], staging_db_path)
        
    # 2. Discover historical community dump URLs
    urls = fetch_dump.get_latest_dump_urls(num_dumps=FETCH_NUM_DAYS)
    logger.info(f"🔄 Starting iterative rolling-window ingest across {len(urls)} daily archives...")
    
    for idx, url in enumerate(urls, 1):
        logger.info("\n" + "-" * 60)
        logger.info(f"📦 ARCHIVE {idx}/{len(urls)}: {url}")
        logger.info("-" * 60)
        
        try:
            # Ensure raw dump dir is clean before starting
            purge_temporary_raw_dumps(DATA_RAW_DUMP)
            
            # Download & extract this specific day's archive
            fetch_dump.download_and_unpack_dump(url, DATA_RAW_DUMP, DATA_RAW_DUMP / "unpacked")
            
            # Ingest valid listens from unpacked directory into staging DB
            clean_duckdb.ingest_into_staging_db([str(DATA_RAW_DUMP / "unpacked" / "**" / "*.listens")], staging_db_path)
            
        except Exception as e:
            logger.error(f"⚠️ Error occurred processing archive {url}: {e}", exc_info=True)
            logger.info("Continuing pipeline with remaining available archives...")
        finally:
            # CRITICAL: Reclaim 3+ GB of disk space immediately
            purge_temporary_raw_dumps(DATA_RAW_DUMP)
            
    # 3. Compile all staged events into deduplicated Parquet dataset
    logger.info("\n⚙️ Compiling staged rolling-window dataset into final Parquet...")
    clean_duckdb.compile_staged_to_parquet(
        staging_db_path, 
        ALL_LISTENS_PARQUET, 
        min_user_plays=MIN_USER_PLAYS, 
        min_artist_plays=MIN_ARTIST_PLAYS
    )
    
    # 4. Remove temporary staging database
    if staging_db_path.exists():
        try:
            staging_db_path.unlink()
            logger.info("✨ Successfully cleaned up persistent DuckDB staging database.")
        except Exception as e:
            logger.warning(f"Could not delete staging DB: {e}")
            
    # 5. Optional cloud sync: Upload cleanly to AWS S3
    bucket = os.getenv("AWS_S3_BUCKET")
    if bucket:
        from src.s3_utils import upload_file
        logger.info(f"☁️ Uploading compiled dataset ({ALL_LISTENS_PARQUET.name}) to AWS S3 ({bucket})...")
        upload_file(ALL_LISTENS_PARQUET, bucket, f"data/processed/{ALL_LISTENS_PARQUET.name}")
        logger.info("✅ AWS S3 sync complete! Overwritten cleanly without version duplication.")

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
    
    # 2. Iterative Rolling-Window Dump Ingestion & DuckDB Compilation
    execute_pipeline_step("2. Iterative Rolling-Window Dump Ingestion & DuckDB Compilation", run_iterative_ingestion_and_cleaning)
    
    # 3. Train Collaborative Filtering ALS Matrix & Push to AWS S3
    execute_pipeline_step("3. Collaborative Filtering ALS Matrix Retraining & S3 Export", train_model.main)
    
    total_duration = round((time.time() - pipeline_start) / 60, 2)
    logger.info("=" * 70)
    logger.info(f"🏆 WEEKLY PIPELINE COMPLETE! Entire rolling-window workflow processed in {total_duration} minutes.")
    logger.info("   -> Newest artist latent embeddings and mappings pushed cleanly to S3.")
    logger.info("   -> Ready for real-time online inference via AWS Lambda.")
    logger.info("=" * 70)

if __name__ == "__main__":
    main()

