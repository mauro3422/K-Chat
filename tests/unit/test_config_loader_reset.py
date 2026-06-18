from src import config_loader


def test_reset_dotenv_state_clears_flag():
    config_loader._dotenv_loaded = True
    config_loader.reset_dotenv_state()
    assert config_loader._dotenv_loaded is False
