from models.user import User
from models.pair import Pair
from models.image import Image
import random
import string
from datetime import datetime, timedelta
from database import db
import os

def generate_pairing_code():
    """Generate a 6-digit pairing code"""
    return ''.join(random.choices(string.digits, k=6))

def cleanup_expired_images():
    """Clean up expired images from database and filesystem"""
    expired_images = Image.query.filter(
        Image.expires_at < datetime.utcnow(),
        Image.status == 'viewed'
    ).all()
    
    for image in expired_images:
        try:
            if os.path.exists(image.file_path):
                os.remove(image.file_path)
        except Exception as e:
            print(f"Error deleting file {image.file_path}: {e}")
        
        image.status = 'expired'
    
    db.session.commit()
    return len(expired_images)
