import os
import time
import logging
from pathlib import Path
import duckdb
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def get_matching_files(patterns):
    """Return a list of file paths matching the provided glob patterns or directory paths."""
    if isinstance(patterns, (str, Path)):
        patterns = [str(patterns)]
    matched = []
    for pat in patterns:
        pat = str(pat)
        pat_obj = Path(pat)
        if "*" in pat or "?" in pat or "**" in pat or "[" in pat:
            # Handle standard recursive patterns or wildcards using Path.glob/rglob
            parts = Path(pat).parts
            idx = next((i for i, p in enumerate(parts) if any(c in p for c in "*?[]")), len(parts))
            base_dir = Path(*parts[:idx]) if idx > 0 else Path(".")
            if base_dir.exists():
                glob_pat = "/".join(parts[idx:])
                matched.extend(list(base_dir.glob(glob_pat)))
        elif pat_obj.is_file():
            matched.append(pat_obj)
        elif pat_obj.is_dir():
            matched.extend(list(pat_obj.rglob("*.listens")) + list(pat_obj.rglob("*.json")))
    return [str(f) for f in matched if f.is_file() and f.stat().st_size > 0]

def ingest_into_staging_db(input_patterns, staging_db_path):
    """
    Ingest raw JSON/listens files into a persistent staging DuckDB table.
    Performs entity resolution and validation per-batch before feature selection.
    """
    staging_db_path = Path(staging_db_path)
    staging_db_path.parent.mkdir(parents=True, exist_ok=True)
    
    matched_files = get_matching_files(input_patterns)
    if not matched_files:
        logger.warning(f"No non-empty matching data files found for patterns: {input_patterns}. Skipping ingestion.")
        return 0
        
    logger.info(f"Ingesting {len(matched_files)} file(s) into staging DB ({staging_db_path.name})...")
    con = duckdb.connect(str(staging_db_path))
    
    con.execute("""
    CREATE TABLE IF NOT EXISTS staged_listens (
        user_name VARCHAR,
        listened_at BIGINT,
        track_name VARCHAR,
        artist_name VARCHAR,
        release_name VARCHAR,
        recording_mbid VARCHAR,
        release_mbid VARCHAR
    );
    """)
    
    schema_declaration = {
        'user_name': 'VARCHAR',
        'timestamp': 'BIGINT',
        'listened_at': 'BIGINT',
        'track_metadata': 'STRUCT(artist_name VARCHAR, track_name VARCHAR, release_name VARCHAR, additional_info STRUCT(recording_mbid VARCHAR, release_mbid VARCHAR))'
    }
    
    # Pass exact verified file paths to DuckDB read_json
    file_list_sql = "[" + ", ".join([f"'{f}'" for f in matched_files]) + "]"
    
    sql_query = rf"""
    INSERT INTO staged_listens
    WITH raw_listens AS (
        SELECT 
            TRIM(user_name) AS user_name,
            COALESCE(listened_at, timestamp) AS listened_at,
            TRIM(track_metadata.track_name) AS raw_track_name,
            TRIM(track_metadata.artist_name) AS raw_artist_name,
            TRIM(track_metadata.release_name) AS release_name,
            COALESCE(track_metadata.additional_info.recording_mbid, '') AS recording_mbid,
            COALESCE(track_metadata.additional_info.release_mbid, '') AS release_mbid
        FROM read_json({file_list_sql}, columns={schema_declaration}, ignore_errors=True)
    ),
    entity_resolution AS (
        -- Step 1: Entity Resolution & String Normalization
        SELECT 
            user_name,
            listened_at,
            TRIM(REGEXP_REPLACE(
                raw_track_name,
                '\s*([-\(\[].*(remaster|remastered|deluxe|bonus|anniversary|mono|stereo|live|edition|acoustic).*[\)\]]?)',
                '',
                'ig'
            )) AS track_name,
            TRIM(REGEXP_REPLACE(raw_artist_name, '\s+', ' ', 'g')) AS artist_name,
            release_name,
            recording_mbid,
            release_mbid
        FROM raw_listens
    ),
    valid_listens AS (
        -- Step 2: Basic Validation (Remove nulls & placeholder junk)
        SELECT *
        FROM entity_resolution
        WHERE user_name IS NOT NULL AND length(user_name) > 0
          AND artist_name IS NOT NULL AND length(artist_name) > 0
          AND track_name IS NOT NULL AND length(track_name) > 0
          AND LOWER(artist_name) NOT IN ('unknown', 'unknown artist', '[unknown]', 'various artists', 'undefined')
    )
    SELECT * FROM valid_listens;
    """
    
    con.execute(sql_query)
    total_staged = con.execute("SELECT COUNT(*) FROM staged_listens").fetchone()[0]
    con.close()
    
    logger.info(f"✅ Batch ingested successfully! Total rows currently staged in DB: {total_staged:,}")
    return len(matched_files)

def compile_staged_to_parquet(staging_db_path, output_file, min_user_plays=10, min_artist_plays=5):
    """
    Compile accumulated staging records into final compressed Parquet table.
    Applies global deduplication and active community feature selection thresholds across the rolling window.
    """
    staging_db_path = Path(staging_db_path)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    if not staging_db_path.exists():
        raise FileNotFoundError(f"Staging database not found at {staging_db_path}")
        
    logger.info(f"Compiling staging DB ({staging_db_path.name}) to final Parquet ({output_file.name})...")
    logger.info(f"Applying Feature Filters: Min User Plays >= {min_user_plays} | Min Artist Plays >= {min_artist_plays} | Global Deduplication = ON")
    
    start_time = time.time()
    con = duckdb.connect(str(staging_db_path))
    
    sql_query = rf"""
    COPY (
        WITH deduplicated AS (
            -- Step 1: Global Deduplication across all historical ingested batches
            SELECT DISTINCT *
            FROM staged_listens
        ),
        active_users AS (
            -- Step 2a: Feature Selection (Active listeners across entire rolling time window)
            SELECT user_name
            FROM deduplicated
            GROUP BY user_name
            HAVING COUNT(*) >= {min_user_plays}
        ),
        meaningful_artists AS (
            -- Step 2b: Feature Selection (Prune long-tail typo/noise artist names)
            SELECT artist_name
            FROM deduplicated
            GROUP BY artist_name
            HAVING COUNT(*) >= {min_artist_plays}
        )
        SELECT d.*
        FROM deduplicated d
        INNER JOIN active_users u ON d.user_name = u.user_name
        INNER JOIN meaningful_artists a ON d.artist_name = a.artist_name
        ORDER BY d.user_name, d.listened_at
    ) TO '{output_file}' (FORMAT PARQUET, COMPRESSION ZSTD);
    """
    
    con.execute(sql_query)
    
    elapsed = time.time() - start_time
    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    
    stats = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT user_name), COUNT(DISTINCT artist_name) FROM '{output_file}'").fetchone()
    con.close()
    
    logger.info("-" * 65)
    logger.info(f"✅ Deduplication & Feature Selection complete in {elapsed:.2f} seconds!")
    logger.info(f"📁 Compiled Parquet Size: {file_size_mb:.2f} MB")
    logger.info(f"📊 Cleaned Dataset Stats:")
    logger.info(f"   -> Total Valid Plays:  {stats[0]:,}")
    logger.info(f"   -> Active Users:       {stats[1]:,}")
    logger.info(f"   -> Unique Artists:     {stats[2]:,}")
    logger.info("-" * 65)

def clean_and_select_features(input_pattern, output_file, min_user_plays=10, min_artist_plays=5):
    """
    Use DuckDB to perform out-of-core Data Cleaning and Feature Selection
    over massive JSON listen dumps directly from disk to Parquet.
    """
    output_file = Path(output_file)
    staging_db = output_file.parent / "temp_staging_listens.duckdb"
    if staging_db.exists():
        try:
            staging_db.unlink()
        except Exception:
            pass
            
    ingested_count = ingest_into_staging_db(input_pattern, staging_db)
    if ingested_count > 0:
        compile_staged_to_parquet(staging_db, output_file, min_user_plays=min_user_plays, min_artist_plays=min_artist_plays)
    else:
        logger.error("No valid listen data files could be ingested.")
        
    if staging_db.exists():
        try:
            staging_db.unlink()
            logger.info("🧹 Cleaned up temporary staging database file.")
        except Exception as e:
            logger.warning(f"Could not remove temporary staging DB: {e}")

def main():
    load_dotenv(override=True)
    from src.config import DATA_RAW_DUMP, DATA_RAW, ALL_LISTENS_PARQUET, MIN_USER_PLAYS, MIN_ARTIST_PLAYS
    
    dump_unpacked = DATA_RAW_DUMP / "unpacked"
    output_file = ALL_LISTENS_PARQUET
    
    # Combine both the massive community dump logs AND our targeted API user JSON files!
    input_patterns = [str(dump_unpacked / "**" / "*.listens"), str(DATA_RAW / "*_listens.json")]
    
    if not list(dump_unpacked.rglob("*.listens")) and not list(DATA_RAW.glob("*_listens.json")):
        logger.error(f"No listening data found. Please run src/fetch_listens.py or src/fetch_dump.py first.")
        return
        
    clean_and_select_features(input_patterns, output_file, min_user_plays=MIN_USER_PLAYS, min_artist_plays=MIN_ARTIST_PLAYS)
    
    # Cloud sync: Only upload the lightweight cleaned Parquet file to AWS S3!
    bucket = os.getenv("AWS_S3_BUCKET")
    if bucket:
        from src.s3_utils import upload_file
        logger.info(f"Uploading cleaned dataset ({output_file.name}) to AWS S3 Bucket ({bucket})...")
        upload_file(output_file, bucket, f"data/processed/{output_file.name}")
        logger.info("✅ AWS S3 sync complete! Your cloud pipeline now has millions of cleaned events.")

if __name__ == "__main__":
    main()

