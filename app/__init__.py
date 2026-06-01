import json
import os
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
    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"),
        template_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "templates"),
    )
    app.config.from_object("config.Config")

    db_path = app.config["DB_PATH"]
    conn = init_db(db_path)
    app.config["DB_CONN"] = conn

    app.config["TFIDF_MODEL"] = _load_tfidf_model(app.config)

    from app.routes import api_bp

    app.register_blueprint(api_bp)

    from app.nlp import nlp_bp

    app.register_blueprint(nlp_bp, url_prefix="/nlp")

    return app
