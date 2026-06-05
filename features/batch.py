"""Batch Generation Feature - Generate multiple scripts"""
from flask import Blueprint, jsonify, request

batch_bp = Blueprint('batch', __name__, url_prefix='/api/teachers/batch')

# TODO: Implement batch endpoints
@batch_bp.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "batch"})
