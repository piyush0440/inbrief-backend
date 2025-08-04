from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
import uuid
from datetime import datetime, timedelta
import requests
from requests.auth import HTTPBasicAuth
import json
import sys
import logging
from logging.handlers import RotatingFileHandler
import traceback
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('app.log', maxBytes=10000, backupCount=3),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv('SECRET_KEY', 'super-secret-key-123')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///inbrief.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

# Configure CORS
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "empId", "phoneLastFour"]
    }
})

# Add CORS headers to all responses
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,empId,phoneLastFour')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Database Models
class NewsPost(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    headline = db.Column(db.String(500))
    description = db.Column(db.Text)
    image_urls = db.Column(db.JSON)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50))
    author = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'headline': self.headline,
            'description': self.description,
            'image_urls': self.image_urls or [],
            'date': self.date.strftime('%Y-%m-%d %H:%M:%S') if self.date else None,
            'category': self.category,
            'author': self.author
        }

# SAP API credentials
SAP_API_USERNAME = os.getenv('SAP_API_USERNAME', "api_user@navitasysi")
SAP_API_PASSWORD = os.getenv('SAP_API_PASSWORD', "api@1234")
SAP_API_BASE_URL = os.getenv('SAP_API_BASE_URL', "https://api44.sapsf.com/odata/v2")

# Allowed employee IDs for admin access
ALLOWED_ADMIN_IDS = {'9025857', '9025676', '9023422'}

# Post categories
POST_CATEGORIES = ['Finance', 'Healthcare', 'Achievement', 'Notice', 'Urgent']

def generate_post_id():
    return str(uuid.uuid4())

def is_post_editable(post_date):
    """Check if post is within 2 hour edit window"""
    if isinstance(post_date, str):
        post_time = datetime.strptime(post_date, '%Y-%m-%d %H:%M:%S')
    else:
        post_time = post_date
    return datetime.now() - post_time <= timedelta(hours=2)

def upload_image_to_cloudinary(file):
    """Upload image to Cloudinary and return URL"""
    try:
        result = cloudinary.uploader.upload(file, folder="inbrief")
        return result['secure_url']
    except Exception as e:
        logger.error(f"Error uploading to Cloudinary: {e}")
        return None

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': 'connected' if db.engine.execute('SELECT 1').scalar() else 'disconnected'
    })

# Employee verification endpoint
@app.route('/api/verify_employee', methods=['GET'])
def verify_employee():
    emp_id = request.headers.get('empId')
    phone_last_four = request.headers.get('phoneLastFour')
    
    logger.info(f"Received verification request - Employee ID: {emp_id}, Phone last four: {phone_last_four}")
    
    if not emp_id or not phone_last_four:
        return jsonify({'error': 'Missing employee ID or phone number', 'verified': False}), 400
    
    try:
        # Build query with all needed fields and expansions
        query = (
            f"{SAP_API_BASE_URL}/EmpJob?$filter=userId eq '{emp_id}'"
            "&$expand=employmentNav/personNav/phoneNav,"
            "employmentNav/personNav/personalInfoNav,"
            "departmentNav,locationNav"
            "&$select=userId,employmentNav/personNav/phoneNav/phoneNumber,"
            "employmentNav/personNav/personalInfoNav/firstName,"
            "employmentNav/personNav/personalInfoNav/lastName,"
            "departmentNav/name,locationNav/name"
            "&$format=json"
        )
        
        logger.info(f"Making SAP API request to: {query}")
        
        response = requests.get(
            query,
            auth=HTTPBasicAuth(SAP_API_USERNAME, SAP_API_PASSWORD),
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"SAP API request failed with status {response.status_code}")
            logger.error(f"Response: {response.text}")
            return jsonify({
                'error': 'Failed to fetch employee data',
                'verified': False
            })
        
        # Parse API response
        data = response.json()
        logger.debug(f"API Response: {json.dumps(data, indent=2)}")
        
        results = data.get('d', {}).get('results', [])
        if not results:
            return jsonify({
                'error': 'Employee not found',
                'verified': False
            })
            
        employee = results[0]
        
        # Get phone number
        employment_nav = employee.get('employmentNav', {})
        person_nav = employment_nav.get('personNav', {})
        phone_nav = person_nav.get('phoneNav', {})
        phone_results = phone_nav.get('results', [])
        
        if not phone_results:
            return jsonify({
                'error': 'Phone number not found for employee',
                'verified': False
            })
        
        phone_number = phone_results[0].get('phoneNumber')
        if not phone_number:
            return jsonify({
                'error': 'Phone number is empty',
                'verified': False
            })
        
        # Clean phone number and compare last 4 digits
        cleaned_phone = ''.join(filter(str.isdigit, phone_number))
        logger.info(f"Comparing phone numbers: {cleaned_phone[-4:]} == {phone_last_four}")
        
        if cleaned_phone[-4:] == phone_last_four:
            # Get employee name
            personal_info = person_nav.get('personalInfoNav', {}).get('results', [{}])[0]
            first_name = personal_info.get('firstName', '')
            last_name = personal_info.get('lastName', '')
            
            # Get department and location
            department = employee.get('departmentNav', {}).get('name', '')
            location = employee.get('locationNav', {}).get('name', '')
            
            logger.info(f"Verification successful for {first_name} {last_name}")
            return jsonify({
                'verified': True,
                'userData': {
                    'empId': emp_id,
                    'name': f"{first_name} {last_name}".strip(),
                    'department': department,
                    'location': location
                }
            })
        else:
            return jsonify({
                'error': 'Invalid phone number',
                'verified': False
            })
            
    except requests.Timeout:
        logger.error("SAP API request timed out")
        return jsonify({
            'error': 'Request timed out',
            'verified': False
        })
    except requests.RequestException as e:
        logger.error(f"SAP API request failed: {e}")
        return jsonify({
            'error': 'Failed to connect to SAP API',
            'verified': False
        })
    except Exception as e:
        logger.error(f"Error during verification: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': 'Internal server error',
            'verified': False
        })

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        emp_id = request.form.get('employee_id')
        phone_last_four = request.form.get('password')
        
        if not emp_id or not phone_last_four:
            return render_template('login.html', error='Employee ID and password are required')
            
        if emp_id not in ALLOWED_ADMIN_IDS:
            return render_template('login.html', error='Unauthorized access')
            
        try:
            # Verify against SAP API
            query = (
                f"{SAP_API_BASE_URL}/EmpJob?$filter=userId eq '{emp_id}'"
                "&$expand=employmentNav/personNav/phoneNav,"
                "employmentNav/personNav/personalInfoNav,"
                "departmentNav,locationNav"
                "&$select=userId,employmentNav/personNav/phoneNav/phoneNumber,"
                "employmentNav/personNav/personalInfoNav/firstName,"
                "employmentNav/personNav/personalInfoNav/lastName,"
                "departmentNav/name,locationNav/name"
                "&$format=json"
            )
            
            response = requests.get(
                query,
                auth=HTTPBasicAuth(SAP_API_USERNAME, SAP_API_PASSWORD),
                timeout=30
            )
            
            if response.status_code != 200:
                return render_template('login.html', error='Failed to verify credentials')
                
            data = response.json()
            results = data.get('d', {}).get('results', [])
            
            if not results:
                return render_template('login.html', error='Employee not found')
                
            employee = results[0]
            employment_nav = employee.get('employmentNav', {})
            person_nav = employment_nav.get('personNav', {})
            phone_nav = person_nav.get('phoneNav', {})
            phone_results = phone_nav.get('results', [])
            
            if not phone_results:
                return render_template('login.html', error='Phone number not found')
                
            phone_number = phone_results[0].get('phoneNumber')
            if not phone_number:
                return render_template('login.html', error='Invalid phone number')
                
            cleaned_phone = ''.join(filter(str.isdigit, phone_number))
            if cleaned_phone[-4:] != phone_last_four:
                return render_template('login.html', error='Invalid credentials')
                
            # Get employee name for display
            personal_info = person_nav.get('personalInfoNav', {}).get('results', [{}])[0]
            first_name = personal_info.get('firstName', '')
            last_name = personal_info.get('lastName', '')
            full_name = f"{first_name} {last_name}".strip()
            
            # Store in session
            session['logged_in'] = True
            session['employee_id'] = emp_id
            session['employee_name'] = full_name
            
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            return render_template('login.html', error='Login failed. Please try again.')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

def login_required(f):
    """Decorator to require login for routes"""
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Admin dashboard route
@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html',
                         employee_name=session.get('employee_name'),
                         categories=POST_CATEGORIES)

# List all posts
@app.route('/api/news/all', methods=['GET'])
def get_all_news():
    try:
        posts = NewsPost.query.order_by(NewsPost.date.desc()).all()
        return jsonify([post.to_dict() for post in posts])
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        return jsonify({'error': 'Failed to fetch news'}), 500

# Add a new post
@app.route('/api/news', methods=['POST'])
@login_required
def add_news():
    headline = request.form.get('headline', '')
    description = request.form.get('description', '')
    category = request.form.get('category')
    images = request.files.getlist('images')
    
    # Allow empty headline but require at least one of: headline, description, or image
    if not headline and not description and not images:
        return jsonify({'error': 'Post must have at least a headline, description, or image.'}), 400
        
    if category and category not in POST_CATEGORIES:
        return jsonify({'error': 'Invalid category'}), 400
        
    image_urls = []
    if images:
        for image in images:
            if image:
                # Upload to Cloudinary
                image_url = upload_image_to_cloudinary(image)
                if image_url:
                    image_urls.append(image_url)
                else:
                    logger.error(f"Failed to upload image: {image.filename}")
                
    post_id = generate_post_id()
    news_item = NewsPost(
        id=post_id,
        headline=headline,
        description=description,
        image_urls=image_urls,
        category=category,
        author=session.get('employee_name')
    )
    
    try:
        db.session.add(news_item)
        db.session.commit()
        return jsonify({'success': True, 'item': news_item.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding news: {e}")
        return jsonify({'error': 'Failed to add news'}), 500

# Edit a post by id
@app.route('/api/news/edit/<post_id>', methods=['POST'])
@login_required
def edit_news(post_id):
    post = NewsPost.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
        
    # Check if post is older than 2 hours
    if not is_post_editable(post.date):
        return jsonify({'error': 'Posts can only be edited within 2 hours of creation'}), 403
        
    headline = request.form.get('headline', '')
    description = request.form.get('description', '')
    category = request.form.get('category')
    images = request.files.getlist('images')
    
    # Allow empty headline but require at least one of: headline, description, or image
    if not headline and not description and not images:
        return jsonify({'error': 'Post must have at least a headline, description, or image.'}), 400
        
    if category and category not in POST_CATEGORIES:
        return jsonify({'error': 'Invalid category'}), 400
        
    post.headline = headline
    post.description = description
    if category:
        post.category = category
        
    if images and len(images) > 0:
        image_urls = []
        for image in images:
            if image:
                # Upload to Cloudinary
                image_url = upload_image_to_cloudinary(image)
                if image_url:
                    image_urls.append(image_url)
        if image_urls:
            post.image_urls = image_urls
            
    post.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
        return jsonify({'success': True, 'item': post.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error editing news: {e}")
        return jsonify({'error': 'Failed to edit news'}), 500

# Delete a post
@app.route('/api/news/delete/<post_id>', methods=['DELETE'])
@login_required
def delete_news(post_id):
    post = NewsPost.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
        
    try:
        # Note: Cloudinary images are not automatically deleted
        # You may want to implement cleanup logic here
        db.session.delete(post)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting news: {e}")
        return jsonify({'error': 'Failed to delete news'}), 500

# Assign admin access
@app.route('/api/assign_admin', methods=['POST'])
@login_required
def assign_admin():
    data = request.get_json()
    emp_id = data.get('empId')

    if not emp_id:
        return jsonify({'error': 'Employee ID is required'}), 400

    try:
        # Verify the requesting user is an admin
        if session.get('employee_id') not in ALLOWED_ADMIN_IDS:
            return jsonify({'error': 'Unauthorized to assign admin access'}), 403

        # Verify the employee exists in SAP before assigning admin
        query = (
            f"{SAP_API_BASE_URL}/EmpJob?$filter=userId eq '{emp_id}'"
            "&$select=userId"
            "&$format=json"
        )
        response = requests.get(
            query,
            auth=HTTPBasicAuth(SAP_API_USERNAME, SAP_API_PASSWORD),
            timeout=30
        )

        if response.status_code != 200:
            logger.error(f"SAP API request failed with status {response.status_code}")
            return jsonify({'error': 'Failed to verify employee'}), 400

        data = response.json()
        results = data.get('d', {}).get('results', [])
        if not results:
            return jsonify({'error': 'Employee not found'}), 404

        # Add the new admin to ALLOWED_ADMIN_IDS
        ALLOWED_ADMIN_IDS.add(emp_id)
        logger.info(f"Admin access granted to Employee ID: {emp_id} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return jsonify({'success': True})
    except requests.Timeout:
        logger.error("SAP API request timed out")
        return jsonify({'error': 'Request timed out'}), 408
    except requests.RequestException as e:
        logger.error(f"SAP API request failed: {e}")
        return jsonify({'error': 'Failed to connect to SAP API'}), 500
    except Exception as e:
        logger.error(f"Error assigning admin: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Internal server error'}), 500

# Initialize database
def init_db():
    with app.app_context():
        db.create_all()
        logger.info("Database initialized")

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Use threaded=True for better handling of concurrent requests
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True) 