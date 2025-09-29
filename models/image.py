from database import db
from datetime import datetime, timedelta
import uuid

class Image(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pair_id = db.Column(db.String(36), nullable=False)
    sender_id = db.Column(db.String(36), nullable=False)
    receiver_id = db.Column(db.String(36), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), default='sent')
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    viewed_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    
    def mark_as_viewed(self):
        self.viewed_at = datetime.utcnow()
        self.expires_at = self.viewed_at + timedelta(seconds=30)
        self.status = 'viewed'
        db.session.commit()
    
    def is_expired(self):
        return self.expires_at and datetime.utcnow() > self.expires_at
    
    def to_dict(self):
        return {
            'id': self.id,
            'pairId': self.pair_id,
            'senderId': self.sender_id,
            'receiverId': self.receiver_id,
            'status': self.status,
            'sentAt': self.sent_at.isoformat(),
            'viewedAt': self.viewed_at.isoformat() if self.viewed_at else None,
            'expiresAt': self.expires_at.isoformat() if self.expires_at else None
        }
