import os
import secrets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import random
import string
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configuration class


class Config:
    # Database configuration
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL:
        # Fix Railway PostgreSQL URL format
        if DATABASE_URL.startswith('postgres://'):
            DATABASE_URL = DATABASE_URL.replace(
                'postgres://', 'postgresql://', 1)
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///flashpair.db'

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_urlsafe(32)
    JWT_SECRET_KEY = os.environ.get(
        'JWT_SECRET_KEY') or secrets.token_urlsafe(32)

    # Upload configuration
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size


app.config.from_object(Config)

# Initialize extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app, origins=["*"])  # Configure as needed for production

# Create upload directory
UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Models


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True,
                         nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    current_pair_code = db.Column(db.String(6), index=True)
    current_pair_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Image(db.Model):
    __tablename__ = 'images'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey(
        'users.id'), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey(
        'users.id'), nullable=False, index=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    sender = db.relationship('User', foreign_keys=[sender_id])
    recipient = db.relationship('User', foreign_keys=[recipient_id])

# Helper function to clean up expired images


def cleanup_expired_images():
    """Clean up images that are older than 30 seconds"""
    try:
        cutoff_time = datetime.utcnow() - timedelta(seconds=30)
        expired_images = Image.query.filter(Image.sent_at < cutoff_time).all()

        for image in expired_images:
            # Delete physical file
            try:
                file_path = os.path.join(UPLOAD_FOLDER, image.filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting file {image.filename}: {e}")

            # Delete from database
            db.session.delete(image)

        if expired_images:
            db.session.commit()
            print(f"Cleaned up {len(expired_images)} expired images")

    except Exception as e:
        print(f"Error during cleanup: {e}")
        db.session.rollback()

# Routes


@app.route('/health', methods=['GET'])
def health_check():
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        db_status = 'connected'
    except:
        db_status = 'error'

    return jsonify({
        'status': 'healthy',
        'message': 'FlashPair backend is running!',
        'database': db_status,
        'database_url': 'postgresql' if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'sqlite',
        'port': os.environ.get('PORT', '5000')
    }), 200


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'message': 'FlashPair Backend API',
        'version': '1.0',
        'status': 'running'
    })


@app.route('/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json()

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password required'}), 400

        username = data['username'].lower().strip()
        password = data['password']

        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400

        user = User(username=username)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        access_token = create_access_token(identity=user.id)
        return jsonify({
            'message': 'User created successfully',
            'access_token': access_token,
            'user': {'id': user.id, 'username': user.username}
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"Registration error: {e}")
        return jsonify({'error': 'Registration failed'}), 500


@app.route('/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password required'}), 400

        username = data['username'].lower().strip()
        password = data['password']

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid credentials'}), 401

        access_token = create_access_token(identity=user.id)
        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'user': {'id': user.id, 'username': user.username}
        }), 200

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500


@app.route('/pair/generate', methods=['POST'])
@jwt_required()
def generate_pair_code():
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)

        if not current_user:
            return jsonify({'error': 'User not found'}), 404

        # Generate 6-digit code
        code = ''.join(random.choices(string.digits, k=6))

        # Ensure uniqueness
        while User.query.filter_by(current_pair_code=code).first():
            code = ''.join(random.choices(string.digits, k=6))

        current_user.current_pair_code = code
        current_user.current_pair_id = None  # Clear existing pair

        db.session.commit()
        return jsonify({'pairCode': code}), 200

    except Exception as e:
        db.session.rollback()
        print(f"Generate pair code error: {e}")
        return jsonify({'error': 'Failed to generate code'}), 500


@app.route('/pair/connect', methods=['POST'])
@jwt_required()
def connect_with_code():
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)

        data = request.get_json()
        if not data or not data.get('code'):
            return jsonify({'error': 'Pair code required'}), 400

        code = data['code'].strip()

        # Find user with this code
        target_user = User.query.filter_by(current_pair_code=code).first()

        if not target_user:
            return jsonify({'error': 'Invalid pairing code'}), 400

        if target_user.id == current_user_id:
            return jsonify({'error': 'Cannot pair with yourself'}), 400

        # Pair both users
        current_user.current_pair_id = target_user.id
        target_user.current_pair_id = current_user_id

        # Clear pair codes
        target_user.current_pair_code = None
        current_user.current_pair_code = None

        db.session.commit()
        return jsonify({
            'message': 'Successfully paired!',
            'pairedWith': target_user.username
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"Pair connect error: {e}")
        return jsonify({'error': 'Pairing failed'}), 500


@app.route('/pair/status', methods=['GET'])
@jwt_required()
def get_pair_status():
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)

        if not current_user:
            return jsonify({'error': 'User not found'}), 404

        if current_user.current_pair_id:
            paired_user = User.query.get(current_user.current_pair_id)
            return jsonify({
                'isPaired': True,
                'pairedWith': paired_user.username if paired_user else None
            }), 200

        return jsonify({'isPaired': False}), 200

    except Exception as e:
        print(f"Pair status error: {e}")
        return jsonify({'error': 'Failed to get pair status'}), 500


@app.route('/pair/disconnect', methods=['POST'])
@jwt_required()
def disconnect():
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)

        if current_user.current_pair_id:
            # Disconnect both users
            paired_user = User.query.get(current_user.current_pair_id)
            if paired_user:
                paired_user.current_pair_id = None

            current_user.current_pair_id = None
            current_user.current_pair_code = None

            db.session.commit()
            return jsonify({'message': 'Disconnected successfully'}), 200

        return jsonify({'message': 'Not paired with anyone'}), 200

    except Exception as e:
        db.session.rollback()
        print(f"Disconnect error: {e}")
        return jsonify({'error': 'Disconnect failed'}), 500


@app.route('/image/upload', methods=['POST'])
@jwt_required()
def upload_image():
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)

        if not current_user.current_pair_id:
            return jsonify({'error': 'Not paired with anyone'}), 400

        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Generate secure filename
        original_filename = secure_filename(file.filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{current_user_id}_{original_filename}"
        file_path = os.path.join(UPLOAD_FOLDER, filename)

        file.save(file_path)

        # Save to database
        image = Image(
            filename=filename,
            sender_id=current_user_id,
            recipient_id=current_user.current_pair_id
        )

        db.session.add(image)
        db.session.commit()

        paired_user = User.query.get(current_user.current_pair_id)
        return jsonify({
            'message': 'Image uploaded successfully',
            'imageId': image.id,
            'sentTo': paired_user.username if paired_user else 'Unknown'
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"Upload error: {e}")
        # Clean up file if database save failed
        try:
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass
        return jsonify({'error': 'Upload failed'}), 500


@app.route('/image/check', methods=['GET'])
@jwt_required()
def check_new_image():
    try:
        cleanup_expired_images()

        current_user_id = get_jwt_identity()

        # Check for new images for the current user
        new_image = Image.query.filter_by(
            recipient_id=current_user_id).order_by(Image.sent_at.desc()).first()

        if new_image:
            # Check if image is still valid (not older than 30 seconds)
            time_diff = (datetime.utcnow() - new_image.sent_at).total_seconds()
            if time_diff > 30:
                # Image expired, delete it
                try:
                    file_path = os.path.join(UPLOAD_FOLDER, new_image.filename)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except:
                    pass
                db.session.delete(new_image)
                db.session.commit()
                return jsonify({'hasNewImage': False})

            return jsonify({
                'hasNewImage': True,
                'imageId': new_image.id,
                'senderId': new_image.sender_id,
                'sentAt': new_image.sent_at.isoformat()
            })

        return jsonify({'hasNewImage': False})

    except Exception as e:
        print(f"Check new image error: {e}")
        return jsonify({'hasNewImage': False})


@app.route('/image/info/<int:image_id>', methods=['GET'])
@jwt_required()
def get_image_info(image_id):
    try:
        cleanup_expired_images()

        current_user_id = get_jwt_identity()

        image = Image.query.filter_by(
            id=image_id, recipient_id=current_user_id).first()
        if not image:
            return jsonify({'error': 'Image not found'}), 404

        # Calculate remaining time
        time_diff = (datetime.utcnow() - image.sent_at).total_seconds()
        time_left = max(0, 30 - time_diff)

        if time_left <= 0:
            # Image expired, delete it
            try:
                file_path = os.path.join(UPLOAD_FOLDER, image.filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            db.session.delete(image)
            db.session.commit()
            return jsonify({'error': 'Image expired'}), 404

        return jsonify({
            'image': {
                'id': image.id,
                'sent_at': image.sent_at.isoformat()
            },
            'timeLeft': time_left
        })

    except Exception as e:
        print(f"Get image info error: {e}")
        return jsonify({'error': 'Failed to get image info'}), 500


@app.route('/image/view/<int:image_id>', methods=['GET'])
@jwt_required()
def view_image(image_id):
    try:
        current_user_id = get_jwt_identity()

        image = Image.query.filter_by(
            id=image_id, recipient_id=current_user_id).first()
        if not image:
            return jsonify({'error': 'Image not found'}), 404

        # Check if expired
        time_diff = (datetime.utcnow() - image.sent_at).total_seconds()
        if time_diff > 30:
            return jsonify({'error': 'Image expired'}), 404

        file_path = os.path.join(UPLOAD_FOLDER, image.filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'Image file not found'}), 404

        return send_file(file_path)

    except Exception as e:
        print(f"View image error: {e}")
        return jsonify({'error': 'Failed to view image'}), 500


def init_db():
    """Initialize database tables"""
    try:
        with app.app_context():
            db.create_all()
            print("✅ Database tables created successfully!")
            return True
    except Exception as e:
        print(f"❌ Error creating database tables: {e}")
        return False


# Application startup
if __name__ == '__main__':
    # Initialize database
    print("🚀 Starting FlashPair Backend...")
    print(
        f"📊 Database: {'PostgreSQL' if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite'}")

    if init_db():
        print("✅ Database initialized successfully!")
    else:
        print("⚠️  Database initialization failed, but continuing...")

    # Get port from environment (Railway sets this)
    port = int(os.environ.get('PORT', 5000))

    print(f"🌐 Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
