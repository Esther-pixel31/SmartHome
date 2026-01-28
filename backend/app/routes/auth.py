from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from ..extensions import db
from ..models import User
from ..utils.validation import require_fields

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    err = require_fields(data, ["email", "password"])
    if err:
        return err

    email = data["email"].strip().lower()
    password = str(data["password"])

    if len(password) < 6:
        return jsonify({"error": "weak_password"}), 400

    exists = User.query.filter_by(email=email).first()
    if exists:
        return jsonify({"error": "email_in_use"}), 409

    u = User(email=email)
    u.set_password(password)

    db.session.add(u)
    db.session.commit()

    token = create_access_token(identity=str(u.id))
    return jsonify({"access_token": token}), 201


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    err = require_fields(data, ["email", "password"])
    if err:
        return err

    email = data["email"].strip().lower()
    password = str(data["password"])

    u = User.query.filter_by(email=email).first()
    if not u or not u.check_password(password):
        return jsonify({"error": "invalid_credentials"}), 401

    token = create_access_token(identity=str(u.id))
    return jsonify({"access_token": token})
