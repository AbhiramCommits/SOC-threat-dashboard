import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    STIX_FEED_PATH = os.path.join(DATA_DIR, "sample_stix_feed.json")
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
