import os
import time
import logging
from pathlib import Path
import duckdb
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def clean_and_select_features(input_pattern, output_file, min_user_plays=10, min_artist_plays=5):
    """
    Use DuckDB to perform out-of-core Data Cleaning and Feature Selection
    over massive JSON listen dumps directly from disk to Parquet.
    """
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Initializing DuckDB out-of-core engine over: {input_pattern}")
    logger.info(f"Applying Feature Filters: Min User Plays >= {min_user_plays} | Min Artist Plays >= {min_artist_plays}")
    
    start_time = time.time()
    
    # We declare explicit schema columns to skip third-party player junk and avoid schema collisions
    schema_declaration = {
        'user_name': 'VARCHAR',
        'timestamp': 'BIGINT',
        'listened_at': 'BIGINT',
        'track_metadata': 'STRUCT(artist_name VARCHAR, track_name VARCHAR, release_name VARCHAR, additional_info STRUCT(recording_mbid VARCHAR, release_mbid VARCHAR))'
    }
    
    json_path = f"'{input_pattern}'" if isinstance(input_pattern, str) else str(input_pattern)
    sql_query = rf"""
    COPY (
        WITH raw_listens AS (
            SELECT 
                TRIM(user_name) AS user_name,
                COALESCE(listened_at, timestamp) AS listened_at,
                TRIM(track_metadata.track_name) AS raw_track_name,
                TRIM(track_metadata.artist_name) AS raw_artist_name,
                TRIM(track_metadata.release_name) AS release_name,
                COALESCE(track_metadata.additional_info.recording_mbid, '') AS recording_mbid,
                COALESCE(track_metadata.additional_info.release_mbid, '') AS release_mbid
            FROM read_json({json_path}, columns={schema_declaration}, ignore_errors=True)
        ),
        entity_resolution AS (
            -- Step 1: Entity Resolution & String Normalization
            -- Strip noisy "(Remastered)", "[Live]", or "(Bonus Track)" tags to deduplicate tracks & artists
            SELECT 
                user_name,
                listened_at,
                -- Remove trailing edition/remaster tags and extra spaces from track names
                TRIM(REGEXP_REPLACE(
                    raw_track_name,
                    '\s*([-\(\[].*(remaster|remastered|deluxe|bonus|anniversary|mono|stereo|live|edition|acoustic).*[\)\]]?)',
                    '',
                    'ig'
                )) AS track_name,
                -- Collapse redundant spaces and standardize artist names
                TRIM(REGEXP_REPLACE(raw_artist_name, '\s+', ' ', 'g')) AS artist_name,
                release_name,
                recording_mbid,
                release_mbid
            FROM raw_listens
        ),
        valid_listens AS (
            -- Step 2: Data Cleaning (Remove Nulls, Whitespace, & Placeholder Junk)
            SELECT *
            FROM entity_resolution
            WHERE user_name IS NOT NULL AND length(user_name) > 0
              AND artist_name IS NOT NULL AND length(artist_name) > 0
              AND track_name IS NOT NULL AND length(track_name) > 0
              AND LOWER(artist_name) NOT IN ('unknown', 'unknown artist', '[unknown]', 'various artists', 'undefined')
        ),
        active_users AS (
            -- Step 2a: Feature Selection (Keep meaningful active listeners)
            SELECT user_name
            FROM valid_listens
            GROUP BY user_name
            HAVING COUNT(*) >= {min_user_plays}
        ),
        meaningful_artists AS (
            -- Step 2b: Feature Selection (Prune long-tail typo artist names played only 1-4 times globally)
            SELECT artist_name
            FROM valid_listens
            GROUP BY artist_name
            HAVING COUNT(*) >= {min_artist_plays}
        )
        -- Step 3: Compile cleanly to high-performance Parquet format
        SELECT v.*
        FROM valid_listens v
        INNER JOIN active_users u ON v.user_name = u.user_name
        INNER JOIN meaningful_artists a ON v.artist_name = a.artist_name
        ORDER BY v.user_name, v.listened_at
    ) TO '{output_file}' (FORMAT PARQUET, COMPRESSION ZSTD);
    """
    
    logger.info("Executing DuckDB SQL transformation (this takes ~5-10 seconds for 5 million rows)...")
    con = duckdb.connect()
    con.execute(sql_query)
    
    elapsed = time.time() - start_time
    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    
    # Query summary metrics directly from the compiled Parquet file
    stats = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT user_name), COUNT(DISTINCT artist_name) FROM '{output_file}'").fetchone()
    logger.info("-" * 65)
    logger.info(f"✅ Data Cleaning & Feature Selection complete in {elapsed:.2f} seconds!")
    logger.info(f"📁 Compiled Parquet Size: {file_size_mb:.2f} MB")
    logger.info(f"📊 Cleaned Dataset Stats:")
    logger.info(f"   -> Total Valid Plays:  {stats[0]:,}")
    logger.info(f"   -> Active Users:       {stats[1]:,}")
    logger.info(f"   -> Unique Artists:     {stats[2]:,}")
    logger.info("-" * 65)

def main():
    load_dotenv(override=True)
    base_dir = Path(__file__).resolve().parent.parent
    dump_unpacked = base_dir / "data" / "raw" / "dump" / "unpacked"
    output_file = base_dir / "data" / "processed" / "all_listens.parquet"
    
    # Combine both the massive community dump logs AND our targeted API user JSON files (like trampakulas)!
    input_patterns = [str(dump_unpacked / "**" / "*.listens"), str(base_dir / "data" / "raw" / "*_listens.json")]
    
    if not list(dump_unpacked.rglob("*.listens")) and not list((base_dir / "data" / "raw").glob("*_listens.json")):
        logger.error(f"No listening data found. Please run src/fetch_listens.py or src/fetch_dump.py first.")
        return
        
    clean_and_select_features(input_patterns, output_file, min_user_plays=10, min_artist_plays=5)
    
    # Cloud sync: Only upload the lightweight cleaned Parquet file to AWS S3!
    bucket = os.getenv("AWS_S3_BUCKET")
    if bucket:
        import sys
        if str(base_dir / "src") not in sys.path:
            sys.path.append(str(base_dir / "src"))
        from s3_utils import upload_file
        logger.info(f"Uploading cleaned dataset ({output_file.name}) to AWS S3 Bucket ({bucket})...")
        upload_file(output_file, bucket, f"data/processed/{output_file.name}")
        logger.info("✅ AWS S3 sync complete! Your cloud pipeline now has millions of cleaned events.")

if __name__ == "__main__":
    main()
