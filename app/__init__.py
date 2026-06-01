import json
import pickle
import sqlite3

from flask import Flask

from app.models import init_db


def _load_tfidf_model(config):
    try:
        with open("outputs/tfidf_model.pkl", "rb") as f:
            return pickle.load(f)
    except (FileNotFoundError, pickle.UnpicklingError):
        return None


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    db_path = app.config["DB_PATH"]
    conn = init_db(db_path)
    app.config["DB_CONN"] = conn

    app.config["TFIDF_MODEL"] = _load_tfidf_model(app.config)

    from app.routes import api_bp

    app.register_blueprint(api_bp)

    from app.nlp import nlp_bp

    app.register_blueprint(nlp_bp, url_prefix="/nlp")

    @app.route("/")
    def index():
        return {"status": "running", "name": "SOC Threat Dashboard"}

    return app
