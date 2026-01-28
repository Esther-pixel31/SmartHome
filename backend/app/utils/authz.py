from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt


def require_any_role(*roles):
    allowed = {r.lower() for r in roles}

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            role = (claims.get("role") or "viewer").lower()

            # admin bypass
            if role == "admin":
                return fn(*args, **kwargs)

            if role not in allowed:
                return jsonify({"error": "forbidden"}), 403

            return fn(*args, **kwargs)
        return wrapper
    return deco


def require_scope(model):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            role = (claims.get("role") or "viewer").lower()
            company_id = claims.get("company_id")

            # admin bypass
            if role == "admin":
                return fn(*args, **kwargs)

            obj_id = kwargs.get("id") or kwargs.get(f"{model.__name__.lower()}_id")
            if not obj_id:
                return jsonify({"error": "scope_check_failed"}), 400

            obj = (
                model.query
                .filter(model.id == int(obj_id), model.company_id == company_id)
                .first()
            )
            if not obj:
                return jsonify({"error": "not_found"}), 404

            return fn(*args, **kwargs)
        return wrapper
    return deco
