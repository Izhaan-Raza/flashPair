from database import db
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.user import User
from models.pair import Pair
from utils.database import generate_pairing_code
from datetime import datetime, timedelta

pair_bp = Blueprint('pair', __name__)

@pair_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_code():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.current_pair_id:
            return jsonify({'error': 'Already paired with someone'}), 400
        
        pairing_code = generate_pairing_code()
        user.pairing_code = pairing_code
        user.pairing_code_expiry = datetime.utcnow() + timedelta(minutes=10)
        
        db.session.commit()
        
        return jsonify({
            'pairingCode': pairing_code,
            'expiresAt': user.pairing_code_expiry.isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@pair_bp.route('/connect', methods=['POST'])
@jwt_required()
def connect():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if not data or not data.get('pairingCode'):
            return jsonify({'error': 'Pairing code required'}), 400
        
        if user.current_pair_id:
            return jsonify({'error': 'Already paired with someone'}), 400
        
        pairing_code = data['pairingCode']
        target_user = User.query.filter_by(pairing_code=pairing_code).first()
        
        if not target_user:
            return jsonify({'error': 'Invalid pairing code'}), 400
        
        if target_user.pairing_code_expiry < datetime.utcnow():
            return jsonify({'error': 'Pairing code expired'}), 400
        
        if target_user.current_pair_id:
            return jsonify({'error': 'User already paired with someone else'}), 400
        
        if target_user.id == user_id:
            return jsonify({'error': 'Cannot pair with yourself'}), 400
        
        # Create pair
        pair = Pair(
            user1_id=user_id,
            user2_id=target_user.id
        )
        db.session.add(pair)
        db.session.flush()  # This ensures pair.id is available
        
        # Update both users
        user.current_pair_id = pair.id
        target_user.current_pair_id = pair.id
        target_user.pairing_code = None
        target_user.pairing_code_expiry = None
        
        db.session.commit()
        
        return jsonify({
            'pairId': pair.id,
            'pairedWith': target_user.username,
            'message': f'Successfully paired with {target_user.username}'
        }), 200
        
    except Exception as e:
        db.session.rollback()  # Add rollback for safety
        return jsonify({'error': str(e)}), 500



@pair_bp.route('/disconnect', methods=['DELETE'])
@jwt_required()
def disconnect():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or not user.current_pair_id:
            return jsonify({'error': 'Not currently paired'}), 400
        
        pair = Pair.query.get(user.current_pair_id)
        if pair:
            other_user_id = pair.get_other_user_id(user_id)
            other_user = User.query.get(other_user_id)
            
            user.current_pair_id = None
            other_user.current_pair_id = None
            pair.status = 'inactive'
            
            db.session.commit()
            
            return jsonify({'message': 'Successfully disconnected'}), 200
        
        return jsonify({'error': 'Pair not found'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@pair_bp.route('/debug', methods=['GET'])
@jwt_required()
def debug():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        all_pairs = Pair.query.all()
        pairs_data = [p.to_dict() for p in all_pairs]
        
        return jsonify({
            'currentUser': user.to_dict(),
            'allPairs': pairs_data
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@pair_bp.route('/status', methods=['GET'])
@jwt_required()
def get_status():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if not user.current_pair_id:
            return jsonify({
                'isPaired': False,
                'pairingCode': user.pairing_code,
                'codeExpiry': user.pairing_code_expiry.isoformat() if user.pairing_code_expiry else None
            }), 200
        
        pair = Pair.query.get(user.current_pair_id)
        if pair:
            other_user_id = pair.get_other_user_id(user_id)
            other_user = User.query.get(other_user_id)
            return jsonify({
                'isPaired': True,
                'pairId': pair.id,
                'pairedWith': other_user.username,
                'pairedSince': pair.created_at.isoformat()
            }), 200
        
        return jsonify({'isPaired': False}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
