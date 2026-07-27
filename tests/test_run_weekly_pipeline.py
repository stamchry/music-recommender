import pytest
from unittest.mock import patch, MagicMock
from src import run_weekly_pipeline

def test_execute_pipeline_step_success():
    mock_fn = MagicMock()
    assert run_weekly_pipeline.execute_pipeline_step("Test Step", mock_fn, 10, key="val") is True
    mock_fn.assert_called_once_with(10, key="val")

def test_execute_pipeline_step_failure():
    def failing_step():
        raise ValueError("Simulated failure")
    with pytest.raises(RuntimeError) as exc_info:
        run_weekly_pipeline.execute_pipeline_step("Failing Step", failing_step)
    assert "aborted during step: Failing Step" in str(exc_info.value)

def test_purge_temporary_raw_dumps(tmp_path):
    dummy_dir = tmp_path / "dump_raw"
    dummy_dir.mkdir()
    (dummy_dir / "large_file.tar.zst").touch()
    run_weekly_pipeline.purge_temporary_raw_dumps(dummy_dir)
    assert not dummy_dir.exists()

@patch("src.run_weekly_pipeline.clean_duckdb.compile_staged_to_parquet")
@patch("src.run_weekly_pipeline.clean_duckdb.ingest_into_staging_db")
@patch("src.run_weekly_pipeline.fetch_dump.download_and_unpack_dump")
@patch("src.run_weekly_pipeline.fetch_dump.get_latest_dump_urls")
@patch("src.run_weekly_pipeline.purge_temporary_raw_dumps")
def test_run_iterative_ingestion_and_cleaning(mock_purge, mock_get_urls, mock_dl, mock_ingest, mock_compile):
    mock_get_urls.return_value = ["http://dummy.url/archive.tar.zst"]
    run_weekly_pipeline.run_iterative_ingestion_and_cleaning()
    mock_get_urls.assert_called_once()
    mock_dl.assert_called_once()
    mock_compile.assert_called_once()
