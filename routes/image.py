from database import db
from flask import Blueprint, request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.user import User
from models.pair import Pair
from models.image import Image
from utils.database import cleanup_expired_images
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
from PIL import Image as PILImage

image_bp = Blueprint('image', __name__)  # THIS LINE WAS MISSING!

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@image_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_image():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or not user.current_pair_id:
            return jsonify({'error': 'Not paired with anyone'}), 400
        
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400
        
        pair = Pair.query.get(user.current_pair_id)
        other_user_id = pair.get_other_user_id(user_id)
        other_user = User.query.get(other_user_id)
        
        existing_image = Image.query.filter_by(
            pair_id=pair.id,
            status='sent'
        ).first()
        
        if existing_image:
            return jsonify({'error': 'Previous image still pending. Only one image at a time.'}), 400
        
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save file without PIL processing to avoid the PIL error
        file.save(file_path)
        
        image = Image(
            pair_id=pair.id,
            sender_id=user_id,
            receiver_id=other_user_id,
            filename=secure_filename(file.filename),
            file_path=file_path
        )
        
        db.session.add(image)
        pair.last_activity = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'imageId': image.id,
            'sentTo': other_user.username,
            'message': 'Image sent successfully'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Add all your other route functions here...
@image_bp.route('/check', methods=['GET'])
@jwt_required()
def check_new_image():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or not user.current_pair_id:
            return jsonify({'hasNewImage': False}), 200
        
        cleanup_expired_images()
        
        new_image = Image.query.filter_by(
            receiver_id=user_id,
            status='sent'
        ).first()
        
        if new_image:
            return jsonify({
                'hasNewImage': True,
                'imageId': new_image.id,
                'senderId': new_image.sender_id,
                'sentAt': new_image.sent_at.isoformat()
            }), 200
        
        return jsonify({'hasNewImage': False}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@image_bp.route('/view/<image_id>', methods=['GET'])
@jwt_required()
def view_image(image_id):
    try:
        user_id = get_jwt_identity()
        
        image = Image.query.get(image_id)
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
        if image.receiver_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        if image.is_expired():
            return jsonify({'error': 'Image has expired'}), 410
        
        if image.status == 'sent':
            image.mark_as_viewed()
        
        if not os.path.exists(image.file_path):
            return jsonify({'error': 'Image file not found'}), 404
        
        return send_file(image.file_path), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@image_bp.route('/info/<image_id>', methods=['GET'])
@jwt_required()
def get_image_info(image_id):
    try:
        user_id = get_jwt_identity()
        
        image = Image.query.get(image_id)
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
        if image.receiver_id != user_id and image.sender_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        return jsonify({
            'image': image.to_dict(),
            'timeLeft': max(0, int((image.expires_at - datetime.utcnow()).total_seconds())) if image.expires_at else None
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
