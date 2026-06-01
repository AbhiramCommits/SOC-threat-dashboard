from flask import Blueprint

nlp_bp = Blueprint("nlp", __name__)


@nlp_bp.route("/")
def nlp_index():
    return {"nlp": "operational"}
