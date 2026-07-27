import os
import pytest
from pathlib import Path
from unittest.mock import patch
import importlib

def test_config_paths():
    from src import config
    assert isinstance(config.PROJECT_ROOT, Path)
    assert isinstance(config.DATA_DIR, Path)
    assert config.DATA_RAW.name == "raw"
    assert config.MODELS_DIR.name == "models"
    assert config.WEB_DIR.name == "web"
    assert config.DATA_RAW_DUMP.name == "dump"

def test_config_env_override():
    with patch.dict(os.environ, {"ALS_FACTORS": "100", "MIN_USER_PLAYS": "15"}, clear=False):
        from src import config
        importlib.reload(config)
        assert config.ALS_FACTORS == 100
        assert config.MIN_USER_PLAYS == 15
    # Reload again after exiting patch context to restore default values
    from src import config
    importlib.reload(config)
