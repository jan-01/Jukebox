from flask import Blueprint

albumsBp = Blueprint("albumsBp", __name__, url_prefix="/users")

@albumsBp.route("/", methods=["GET"])
def getAlbums():
    return "<p>Hello, World2!</p>"

@albumsBp.route("/<int:albumId>", methods=["GET"])
def getAlbum(albumId):
    return f"{albumId}"