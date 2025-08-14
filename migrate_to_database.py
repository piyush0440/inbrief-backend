#!/usr/bin/env python3
"""
Migration script to move from in-memory storage to database storage
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import NewsPost
import json

def migrate_data():
    """Migrate existing data to database"""
    with app.app_context():
        print("🔄 Starting database migration...")
        
        # Create tables
        db.create_all()
        print("✅ Database tables created")
        
        # Check if there's any existing data to migrate
        existing_posts = NewsPost.query.count()
        if existing_posts > 0:
            print(f"ℹ️  Found {existing_posts} existing posts in database")
            return
        
        # For now, we'll create some sample data since in-memory data is lost
        # In a real scenario, you would migrate from the in-memory list
        sample_posts = [
            {
                'id': 'sample-1',
                'headline': 'Welcome to InBrief',
                'description': 'This is a sample post to demonstrate the new persistent storage system.',
                'image_urls': [],
                'date': '2024-01-01 12:00:00',
                'category': 'Notice',
                'author': 'System'
            },
            {
                'id': 'sample-2',
                'headline': 'Database Migration Complete',
                'description': 'The backend has been successfully migrated to use persistent database storage. Posts will no longer be lost when the server restarts.',
                'image_urls': [],
                'date': '2024-01-01 12:01:00',
                'category': 'Achievement',
                'author': 'System'
            }
        ]
        
        print(f"📝 Creating {len(sample_posts)} sample posts...")
        
        for post_data in sample_posts:
            new_post = NewsPost(
                id=post_data['id'],
                headline=post_data['headline'],
                description=post_data['description'],
                image_urls=json.dumps(post_data['image_urls']),
                date=post_data['date'],
                category=post_data['category'],
                author=post_data['author']
            )
            db.session.add(new_post)
        
        db.session.commit()
        print("✅ Sample posts created successfully!")
        
        # Verify migration
        total_posts = NewsPost.query.count()
        print(f"📊 Total posts in database: {total_posts}")

def verify_database():
    """Verify database is working correctly"""
    with app.app_context():
        print("\n🔍 Verifying database...")
        
        posts = NewsPost.query.all()
        print(f"📝 Found {len(posts)} posts in database")
        
        for i, post in enumerate(posts):
            print(f"  {i+1}. {post.headline} (ID: {post.id})")
            print(f"     Author: {post.author}")
            print(f"     Date: {post.date}")
            print(f"     Images: {len(json.loads(post.image_urls) if post.image_urls else [])}")
            print()

if __name__ == "__main__":
    try:
        migrate_data()
        verify_database()
        print("\n🎉 Migration completed successfully!")
        print("💡 Your posts will now persist across server restarts!")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
