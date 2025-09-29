from database import db
from datetime import datetime
import uuid

class Pair(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user1_id = db.Column(db.String(36), nullable=False)
    user2_id = db.Column(db.String(36), nullable=False)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_other_user_id(self, user_id):
        return self.user2_id if self.user1_id == user_id else self.user1_id
    
    def to_dict(self):
        return {
            'id': self.id,
            'user1Id': self.user1_id,
            'user2Id': self.user2_id,
            'status': self.status,
            'createdAt': self.created_at.isoformat(),
            'lastActivity': self.last_activity.isoformat()
        }
