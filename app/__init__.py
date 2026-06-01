from flask import Flask


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    from app.nlp import nlp_bp

    app.register_blueprint(nlp_bp, url_prefix="/nlp")

    @app.route("/")
    def index():
        return {"status": "running", "name": "SOC Threat Dashboard"}

    return app
