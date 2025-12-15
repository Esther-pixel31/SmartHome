from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from ..extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from ..models import Property

bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Stub for now
@bp.route('/login', methods=['POST'])
def login():
    return jsonify({ 'token': 'dev-token' })
