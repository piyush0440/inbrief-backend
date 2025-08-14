from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class NewsPost(db.Model):
    __tablename__ = 'news_posts'
    
    id = db.Column(db.String(36), primary_key=True)
    headline = db.Column(db.String(500))
    description = db.Column(db.Text)
    image_urls = db.Column(db.Text)  # JSON string
    date = db.Column(db.String(20))
    category = db.Column(db.String(50))
    author = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """Convert database record to dictionary format"""
        return {
            'id': self.id,
            'headline': self.headline or '',
            'description': self.description or '',
            'image_urls': json.loads(self.image_urls) if self.image_urls else [],
            'date': self.date,
            'category': self.category,
            'author': self.author
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create NewsPost instance from dictionary"""
        return cls(
            id=data.get('id'),
            headline=data.get('headline', ''),
            description=data.get('description', ''),
            image_urls=json.dumps(data.get('image_urls', [])),
            date=data.get('date'),
            category=data.get('category'),
            author=data.get('author', '')
        )
