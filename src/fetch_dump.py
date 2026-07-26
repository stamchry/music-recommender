import os
import re
import sys
import tarfile
import logging
from pathlib import Path
import urllib.parse
import requests
from tqdm import tqdm
import zstandard as zstd
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

INDEX_URL = "https://data.musicbrainz.org/pub/musicbrainz/listenbrainz/incremental/"

def get_latest_dump_url():
    """Scrape the incremental dump index to find the latest listens .tar.zst archive."""
    logger.info(f"Querying index at {INDEX_URL}...")
    response = requests.get(INDEX_URL, timeout=15)
    response.raise_for_status()
    
    # Find all incremental folder names (e.g. listenbrainz-dump-2605-20260724-000003-incremental)
    folders = re.findall(r'href="([^"]+incremental/?)"', response.text)
    if not folders:
        raise ValueError("Could not find any incremental dump directories on server.")
        
    # Sort folders alphabetically; since they contain dates (YYYYMMDD), alphabetical is chronological
    folders = sorted(list(set(folders)))
    latest_folder = folders[-1].rstrip('/') + '/'
    folder_url = urllib.parse.urljoin(INDEX_URL, latest_folder)
    
    logger.info(f"Latest dump directory identified: {folder_url}")
    folder_resp = requests.get(folder_url, timeout=15)
    folder_resp.raise_for_status()
    
    # Find the listens-dump tar.zst archive
    archives = re.findall(r'href="(listenbrainz-listens-dump-[^"]+\.tar\.zst)"', folder_resp.text)
    if not archives:
        # Fallback to second latest folder if current day is still generating
        logger.warning(f"No completed archive in {latest_folder}, checking previous day...")
        latest_folder = folders[-2].rstrip('/') + '/'
        folder_url = urllib.parse.urljoin(INDEX_URL, latest_folder)
        folder_resp = requests.get(folder_url, timeout=15)
        archives = re.findall(r'href="(listenbrainz-listens-dump-[^"]+\.tar\.zst)"', folder_resp.text)
        
    if not archives:
        raise ValueError("Could not locate a listenbrainz-listens-dump tar.zst archive.")
        
    archive_url = urllib.parse.urljoin(folder_url, archives[0])
    return archive_url

def download_file(url, target_path):
    """Download file with a visual tqdm progress bar."""
    if target_path.exists():
        logger.info(f"Archive {target_path.name} already exists locally. Skipping download.")
        return

    logger.info(f"Downloading archive from {url}...")
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    block_size = 1024 * 64  # 64 KB
    
    with open(target_path, "wb") as f, tqdm(
        desc=target_path.name,
        total=total_size,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
    ) as progress_bar:
        for data in response.iter_content(block_size):
            f.write(data)
            progress_bar.update(len(data))
            
    logger.info("Download complete!")

def unpack_zst_tar(archive_path, output_dir):
    """Decompress .tar.zst archive and extract files to output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if we already unpacked files
    existing_files = list(output_dir.rglob("*.json*")) + list(output_dir.rglob("*.log")) + list(output_dir.rglob("*.tsv"))
    if existing_files:
        logger.info(f"Found {len(existing_files)} already extracted data files in {output_dir}. Skipping decompression.")
        return

    logger.info(f"Decompressing and unpacking {archive_path.name} (this may take a minute)...")
    dctx = zstd.ZstdDecompressor()
    
    with open(archive_path, "rb") as compressed:
        with dctx.stream_reader(compressed) as reader:
            with tarfile.open(fileobj=reader, mode="r|*") as tar:
                tar.extractall(path=output_dir, filter='data')
                
    extracted = [f for f in output_dir.rglob("*") if f.is_file()]
    logger.info(f"Successfully extracted {len(extracted)} files into {output_dir}:")
    for file in extracted[:5]:
        logger.info(f"  -> {file.relative_to(output_dir)} ({file.stat().st_size / (1024*1024):.2f} MB)")
    if len(extracted) > 5:
        logger.info(f"  ... and {len(extracted) - 5} more files.")

def main():
    load_dotenv(override=True)
    from src.config import DATA_RAW_DUMP
    dump_dir = DATA_RAW_DUMP
    unpacked_dir = dump_dir / "unpacked"
    dump_dir.mkdir(parents=True, exist_ok=True)
    
    # Optional override from environment or command line
    custom_url = os.getenv("LISTENBRAINZ_DUMP_URL")
    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        custom_url = sys.argv[1]
        
    try:
        url = custom_url if custom_url else get_latest_dump_url()
        filename = url.split('/')[-1]
        archive_path = dump_dir / filename
        
        download_file(url, archive_path)
        unpack_zst_tar(archive_path, unpacked_dir)
        
        # S3 optional backup of archive if desired
        bucket = os.getenv("AWS_S3_BUCKET")
        if bucket and os.getenv("UPLOAD_DUMPS_TO_S3", "false").lower() == "true":
            from src.s3_utils import upload_file
            upload_file(archive_path, bucket, f"data/raw/dump/{archive_path.name}")
            
        logger.info("\n✅ Dump ingestion finished! Ready for out-of-core DuckDB cleaning.")
    except Exception as e:
        logger.error(f"Error during dump fetch: {e}", exc_info=True)

if __name__ == "__main__":
    main()
