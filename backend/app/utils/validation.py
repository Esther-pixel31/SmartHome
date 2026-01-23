from flask import jsonify


def require_fields(data, fields):
    if data is None:
        return jsonify({"error": "invalid_json"}), 400

    missing = [f for f in fields if f not in data or data[f] in ("", None)]
    if missing:
        return jsonify({"error": "missing_fields", "fields": missing}), 400

    return None
