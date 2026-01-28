from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from ..extensions import db
from ..models import User, RevokedToken, Company
from ..utils.validation import require_fields
from datetime import datetime

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _claims_for_user(u: User) -> dict:
    return {
        "role": u.role,
        "company_id": u.company_id,
    }


@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    err = require_fields(data, ["email", "password", "company_id"])
    if err:
        return err

    email = data["email"].strip().lower()
    password = str(data["password"])
    company_id = data["company_id"]

    company_id = int(company_id)
    company = Company.query.get(company_id)

    if not company:
        return jsonify({"error": "company_not_found"}), 404

    if len(password) < 6:
        return jsonify({"error": "weak_password"}), 400

    exists = User.query.filter_by(email=email).first()
    if exists:
        return jsonify({"error": "email_in_use"}), 409

    u = User(email=email, company_id=company_id)
    u.set_password(password)

    db.session.add(u)
    db.session.flush()

    # self-created account
    if hasattr(u, "created_by_id"):
        u.created_by_id = u.id

    db.session.commit()

    claims = _claims_for_user(u)
    access_token = create_access_token(identity=str(u.id), additional_claims=claims)
    refresh_token = create_refresh_token(identity=str(u.id), additional_claims=claims)

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
    }), 201


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

    if getattr(u, "deleted_at", None) is not None:
        return jsonify({"error": "account_disabled"}), 403

    if not getattr(u, "company_id", None):
        return jsonify({"error": "account_unscoped"}), 403

    claims = _claims_for_user(u)
    access_token = create_access_token(identity=str(u.id), additional_claims=claims)
    refresh_token = create_refresh_token(identity=str(u.id), additional_claims=claims)

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
    })


@bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    claims = get_jwt()
    role = claims.get("role", "viewer")
    company_id = claims.get("company_id")

    access_token = create_access_token(
        identity=str(user_id),
        additional_claims={"role": role, "company_id": company_id},
    )
    return jsonify({"access_token": access_token})


@bp.route("/logout", methods=["POST"])
@jwt_required()
def logout_access():
    payload = get_jwt()
    jti = payload["jti"]
    token_type = payload["type"]
    user_id = int(get_jwt_identity())
    exp = payload["exp"]

    item = RevokedToken(
        jti=jti,
        token_type=token_type,
        user_id=user_id,
        expires_at=datetime.utcfromtimestamp(exp),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"message": "logged out"}), 200


@bp.route("/logout-refresh", methods=["POST"])
@jwt_required(refresh=True)
def logout_refresh():
    payload = get_jwt()
    jti = payload["jti"]
    token_type = payload["type"]
    user_id = int(get_jwt_identity())
    exp = payload["exp"]

    item = RevokedToken(
        jti=jti,
        token_type=token_type,
        user_id=user_id,
        expires_at=datetime.utcfromtimestamp(exp),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"message": "refresh logged out"}), 200
