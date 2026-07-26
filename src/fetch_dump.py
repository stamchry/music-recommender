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

def get_latest_dump_urls(num_dumps=7):
    """Scrape the incremental dump index to find the latest N daily listens .tar.zst archives."""
    logger.info(f"Querying index at {INDEX_URL} for the latest {num_dumps} dumps...")
    response = requests.get(INDEX_URL, timeout=15)
    response.raise_for_status()
    
    # Find all incremental folder names (e.g. listenbrainz-dump-2605-20260724-000003-incremental)
    folders = re.findall(r'href="([^"]+incremental/?)"', response.text)
    if not folders:
        raise ValueError("Could not find any incremental dump directories on server.")
        
    # Sort folders alphabetically; since they contain dates (YYYYMMDD), alphabetical is chronological
    folders = sorted(list(set(folders)))
    
    archive_urls = []
    # Traverse backward from most recent folder until we gather requested number of completed dumps
    for folder in reversed(folders):
        if len(archive_urls) >= num_dumps:
            break
        folder_clean = folder.rstrip('/') + '/'
        folder_url = urllib.parse.urljoin(INDEX_URL, folder_clean)
        try:
            folder_resp = requests.get(folder_url, timeout=15)
            if folder_resp.status_code == 200:
                archives = re.findall(r'href="(listenbrainz-listens-dump-[^"]+\.tar\.zst)"', folder_resp.text)
                if archives:
                    archive_url = urllib.parse.urljoin(folder_url, archives[0])
                    archive_urls.append(archive_url)
                else:
                    logger.debug(f"No archive found in {folder_clean}, possibly still generating.")
        except Exception as e:
            logger.warning(f"Failed to check folder {folder_clean}: {e}")
            
    if not archive_urls:
        raise ValueError("Could not locate any valid listenbrainz-listens-dump tar.zst archives.")
        
    # Reverse to process chronologically (oldest to newest)
    archive_urls.reverse()
    logger.info(f"Successfully discovered {len(archive_urls)} archive dump URLs.")
    return archive_urls

def get_latest_dump_url():
    """Scrape the incremental dump index to find the single latest listens .tar.zst archive."""
    urls = get_latest_dump_urls(num_dumps=1)
    return urls[-1] if urls else None

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
    """Decompress .tar.zst archive and extract files to an archive-specific directory in output_dir."""
    output_dir = Path(output_dir)
    archive_dir = output_dir / archive_path.name.replace('.tar.zst', '').replace('.tar', '')
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if we already unpacked this specific archive
    existing_files = list(archive_dir.rglob("*.listens")) + list(archive_dir.rglob("*.json*"))
    if existing_files:
        logger.info(f"Found {len(existing_files)} extracted files in {archive_dir}. Skipping decompression.")
        return archive_dir

    logger.info(f"Decompressing and unpacking {archive_path.name} into {archive_dir}...")
    dctx = zstd.ZstdDecompressor()
    
    with open(archive_path, "rb") as compressed:
        with dctx.stream_reader(compressed) as reader:
            with tarfile.open(fileobj=reader, mode="r|*") as tar:
                tar.extractall(path=archive_dir, filter='data')
                
    extracted = [f for f in archive_dir.rglob("*") if f.is_file()]
    logger.info(f"Successfully extracted {len(extracted)} files into {archive_dir}:")
    for file in extracted[:5]:
        logger.info(f"  -> {file.relative_to(archive_dir)} ({file.stat().st_size / (1024*1024):.2f} MB)")
    if len(extracted) > 5:
        logger.info(f"  ... and {len(extracted) - 5} more files.")
    return archive_dir

def download_and_unpack_dump(url, dump_dir, unpacked_dir):
    """Download and extract a specific dump archive URL into target directories."""
    dump_dir = Path(dump_dir)
    unpacked_dir = Path(unpacked_dir)
    dump_dir.mkdir(parents=True, exist_ok=True)
    unpacked_dir.mkdir(parents=True, exist_ok=True)
    
    filename = url.split('/')[-1]
    archive_path = dump_dir / filename
    
    download_file(url, archive_path)
    unpack_zst_tar(archive_path, unpacked_dir)
    
    # Optional S3 backup of raw archive if desired
    bucket = os.getenv("AWS_S3_BUCKET")
    if bucket and os.getenv("UPLOAD_DUMPS_TO_S3", "false").lower() == "true":
        from src.s3_utils import upload_file
        upload_file(archive_path, bucket, f"data/raw/dump/{archive_path.name}")
        
    return archive_path

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
        if custom_url:
            urls = [custom_url]
        else:
            # For standalone command line execution, check FETCH_NUM_DAYS (defaults to 1 for quick experimentation)
            num_dumps = int(os.getenv("FETCH_NUM_DAYS", "1"))
            urls = get_latest_dump_urls(num_dumps=num_dumps)
            
        for idx, url in enumerate(urls, 1):
            logger.info(f"\n--- Ingesting archive {idx}/{len(urls)}: {url} ---")
            download_and_unpack_dump(url, dump_dir, unpacked_dir)
            
        logger.info("\n✅ Dump ingestion finished! Ready for out-of-core DuckDB cleaning.")
    except Exception as e:
        logger.error(f"Error during dump fetch: {e}", exc_info=True)

if __name__ == "__main__":
    main()

