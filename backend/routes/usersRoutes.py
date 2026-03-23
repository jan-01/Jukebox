from flask import Blueprint

usersBp = Blueprint("userBP", __name__, url_prefix="/users")

@usersBp.route("/", methods=["GET"])
def getUsers():
    return "<p>Hello, World2!</p>"

@usersBp.route("/<int:userId>", methods=["GET"])
def getUser(userId):
    return f"{userId}"