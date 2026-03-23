from flask import Blueprint

songsBp = Blueprint("songsBp", __name__, url_prefix="/users")

@songsBp.route("/", methods=["GET"])
def getSongs():
    return "<p>Hello, World2!</p>"

@songsBp.route("/<int:songId>", methods=["GET"])
def getSong(songId):
    return f"{songId}"