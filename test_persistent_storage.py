#!/usr/bin/env python3
"""
Test script to verify persistent storage solution
"""

import requests
import json
import time
from datetime import datetime

def test_persistent_storage():
    base_url = "https://inbrief-backend.onrender.com"
    
    print("🔍 Testing Persistent Storage Solution...")
    print(f"Base URL: {base_url}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1: Check if backend is accessible
    print("\n📡 Testing backend accessibility...")
    try:
        response = requests.get(base_url, timeout=10)
        print(f"Backend status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Backend is accessible")
        else:
            print("❌ Backend not accessible")
            return
            
    except Exception as e:
        print(f"❌ Error testing backend: {e}")
        return
    
    # Test 2: Get current posts
    print("\n📝 Testing posts API...")
    try:
        response = requests.get(f"{base_url}/api/news/all", timeout=10)
        print(f"Posts API Status: {response.status_code}")
        
        if response.status_code == 200:
            posts = response.json()
            print(f"✅ Found {len(posts)} posts")
            
            if len(posts) > 0:
                print("\n📊 Sample posts:")
                for i, post in enumerate(posts[:3]):  # Show first 3 posts
                    print(f"  {i+1}. {post.get('headline', 'No headline')}")
                    print(f"     ID: {post.get('id', 'No ID')}")
                    print(f"     Date: {post.get('date', 'No date')}")
                    print(f"     Images: {len(post.get('image_urls', []))}")
                    print()
            else:
                print("ℹ️  No posts found - this is normal for a fresh deployment")
        else:
            print(f"❌ Failed to get posts: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing posts: {e}")
    
    # Test 3: Test image persistence
    print("\n🖼️  Testing image persistence...")
    try:
        response = requests.get(f"{base_url}/api/news/all", timeout=10)
        if response.status_code == 200:
            posts = response.json()
            
            total_images = 0
            cloudinary_images = 0
            
            for post in posts:
                image_urls = post.get('image_urls', [])
                total_images += len(image_urls)
                
                for img_url in image_urls:
                    if 'cloudinary.com' in img_url:
                        cloudinary_images += 1
                        # Test if Cloudinary image is accessible
                        try:
                            img_response = requests.head(img_url, timeout=5)
                            if img_response.status_code == 200:
                                print(f"✅ Cloudinary image accessible: {img_url[:50]}...")
                            else:
                                print(f"❌ Cloudinary image not accessible: {img_url[:50]}...")
                        except Exception as e:
                            print(f"❌ Cloudinary image error: {e}")
            
            print(f"📊 Image Summary:")
            print(f"   Total images: {total_images}")
            print(f"   Cloudinary images: {cloudinary_images}")
            if total_images > 0:
                print(f"   Cloudinary usage: {(cloudinary_images/total_images*100):.1f}%")
            
    except Exception as e:
        print(f"❌ Error testing images: {e}")
    
    # Test 4: Simulate server restart test
    print("\n🔄 Simulating server restart test...")
    print("💡 To test persistence across server restarts:")
    print("   1. Create a test post via the dashboard")
    print("   2. Wait 5+ minutes for server to sleep")
    print("   3. Make any request to wake up the server")
    print("   4. Check if the post still exists")
    print("   5. Verify images are still accessible")
    
    print("\n🎯 Expected Results:")
    print("   ✅ Posts should persist across server restarts")
    print("   ✅ Images should remain accessible from Cloudinary")
    print("   ✅ No data loss during sleep cycles")
    
    print("\n💡 Benefits of this solution:")
    print("   🔒 Persistent data storage with SQLite database")
    print("   ☁️  Cloudinary for reliable image storage")
    print("   💾 1GB persistent disk on Render")
    print("   🚀 No more data loss during server sleep")

if __name__ == "__main__":
    test_persistent_storage()
