import logging
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from src import fetch_dump

@patch("src.fetch_dump.requests.get")
def test_get_latest_dump_urls(mock_get):
    root_resp = MagicMock()
    root_resp.status_code = 200
    root_resp.text = '<a href="listenbrainz-dump-20260724-incremental/">dir</a>'
    
    sub_resp = MagicMock()
    sub_resp.status_code = 200
    sub_resp.text = '<a href="listenbrainz-listens-dump-20260724.tar.zst">archive</a>'
    
    mock_get.side_effect = [root_resp, sub_resp]
    urls = fetch_dump.get_latest_dump_urls(num_dumps=1)
    assert len(urls) == 1
    assert "listenbrainz-listens-dump-20260724.tar.zst" in urls[0]

@patch("src.fetch_dump.get_latest_dump_urls")
def test_get_latest_dump_url(mock_urls):
    mock_urls.return_value = ["http://example.com/dump1.tar.zst", "http://example.com/dump2.tar.zst"]
    assert fetch_dump.get_latest_dump_url() == "http://example.com/dump2.tar.zst"

def test_download_file_skip_existing(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    f = tmp_path / "archive.tar.zst"
    f.touch()
    fetch_dump.download_file("http://dummy.url/archive.tar.zst", f)
    assert "already exists locally. Skipping download." in caplog.text

@patch("src.fetch_dump.requests.get")
def test_download_file_success(mock_get, tmp_path):
    mock_resp = MagicMock()
    mock_resp.headers = {"content-length": "10"}
    mock_resp.iter_content.return_value = [b"1234567890"]
    mock_get.return_value = mock_resp
    
    target = tmp_path / "new_archive.tar.zst"
    fetch_dump.download_file("http://dummy.url/new_archive.tar.zst", target)
    assert target.exists()
    assert target.read_bytes() == b"1234567890"

def test_unpack_zst_tar_existing(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir(parents=True)
    existing_file = archive_dir / "test.listens"
    existing_file.touch()
    
    dummy_tar = tmp_path / "archive.tar.zst"
    dummy_tar.touch()
    
    res = fetch_dump.unpack_zst_tar(dummy_tar, tmp_path)
    assert "Skipping decompression" in caplog.text
    assert res == archive_dir
