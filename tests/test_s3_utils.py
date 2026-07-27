import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from src import s3_utils

@patch("src.s3_utils.get_s3_client")
def test_create_bucket_us_east_1(mock_client_fn):
    mock_s3 = MagicMock()
    mock_client_fn.return_value = mock_s3
    assert s3_utils.create_bucket("my-test-bucket", region="us-east-1") is True
    mock_s3.create_bucket.assert_called_once_with(Bucket="my-test-bucket")

@patch("src.s3_utils.get_s3_client")
def test_create_bucket_other_region(mock_client_fn):
    mock_s3 = MagicMock()
    mock_client_fn.return_value = mock_s3
    assert s3_utils.create_bucket("my-test-bucket", region="eu-west-1") is True
    mock_s3.create_bucket.assert_called_once_with(
        Bucket="my-test-bucket",
        CreateBucketConfiguration={"LocationConstraint": "eu-west-1"}
    )

@patch("src.s3_utils.get_s3_client")
def test_upload_file_error(mock_client_fn, tmp_path):
    mock_s3 = MagicMock()
    mock_s3.upload_file.side_effect = ClientError({"Error": {"Code": "403"}}, "upload_file")
    mock_client_fn.return_value = mock_s3
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    assert s3_utils.upload_file(test_file, "bucket", "key") is False

@patch("src.s3_utils.get_s3_client")
def test_upload_file_success(mock_client_fn, tmp_path):
    mock_s3 = MagicMock()
    mock_client_fn.return_value = mock_s3
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    assert s3_utils.upload_file(test_file, "bucket", "key") is True
    mock_s3.upload_file.assert_called_once()

@patch("src.s3_utils.get_s3_client")
def test_download_file(mock_client_fn, tmp_path):
    mock_s3 = MagicMock()
    mock_client_fn.return_value = mock_s3
    dest_file = tmp_path / "subdir" / "downloaded.txt"
    assert s3_utils.download_file("bucket", "key", dest_file) is True
    mock_s3.download_file.assert_called_once_with("bucket", "key", str(dest_file))
    assert dest_file.parent.exists()

@patch("src.s3_utils.get_s3_resource")
def test_download_directory(mock_resource_fn, tmp_path):
    mock_s3_resource = MagicMock()
    mock_bucket = MagicMock()
    mock_obj = MagicMock()
    mock_obj.key = "prefix/test_data.txt"
    mock_bucket.objects.filter.return_value = [mock_obj]
    mock_s3_resource.Bucket.return_value = mock_bucket
    mock_resource_fn.return_value = mock_s3_resource
    
    assert s3_utils.download_directory("bucket", "prefix", tmp_path) is True
    mock_bucket.download_file.assert_called_once_with("prefix/test_data.txt", str(tmp_path / "test_data.txt"))

@patch("src.s3_utils.get_s3_client")
def test_upload_directory(mock_client_fn, tmp_path):
    mock_s3 = MagicMock()
    mock_client_fn.return_value = mock_s3
    sub = tmp_path / "subdir"
    sub.mkdir()
    f1 = tmp_path / "file1.txt"
    f2 = sub / "file2.txt"
    f1.write_text("data1")
    f2.write_text("data2")
    assert s3_utils.upload_directory(tmp_path, "bucket", "prefix") is True
    assert mock_s3.upload_file.call_count == 2
