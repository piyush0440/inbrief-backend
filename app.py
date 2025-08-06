from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session
from flask_cors import CORS
import os
import uuid
from datetime import datetime, timedelta
import pytz
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
import cloudinary.api

# Load environment variables
load_dotenv()

# Cloudinary Configuration
cloudinary.config(
    cloud_name="dttnc46ds",
    api_key="564877812975431",
    api_secret="AJ1yEajONIlJA5cwgLc-gP2fIto"
)

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

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.getenv('SECRET_KEY', 'super-secret-key-123')  # Use environment variable
UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure CORS to allow requests from any origin
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

# SAP API credentials from environment variables
SAP_API_USERNAME = os.getenv('SAP_API_USERNAME', "api_user@navitasysi")
SAP_API_PASSWORD = os.getenv('SAP_API_PASSWORD', "api@1234")
SAP_API_BASE_URL = os.getenv('SAP_API_BASE_URL', "https://api44.sapsf.com/odata/v2")

# Allowed employee IDs for admin access from environment variable
ALLOWED_ADMIN_IDS_STR = os.getenv('ALLOWED_ADMIN_IDS', '9025857,9025676,9023422')
ALLOWED_ADMIN_IDS = set(ALLOWED_ADMIN_IDS_STR.split(','))

# Post categories
POST_CATEGORIES = ['Finance', 'Healthcare', 'Achievement', 'Notice', 'Urgent']

# In-memory storage for demo (replace with DB in production)
news_posts = []

def generate_post_id():
    return str(uuid.uuid4())

def is_post_editable(post_date):
    """Check if post is within 2 hour edit window"""
    ist = pytz.timezone('Asia/Kolkata')
    post_time = datetime.strptime(post_date, '%Y-%m-%d %H:%M:%S')
    post_time = ist.localize(post_time)
    current_time = datetime.now(ist)
    return current_time - post_time <= timedelta(hours=2)

# Add back the mobile app verification endpoint
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
    all_posts = [post.copy() for post in news_posts]
    # Sort by date (descending)
    all_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
    return jsonify(all_posts)

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
                try:
                    # Upload to Cloudinary with your specific configuration
                    result = cloudinary.uploader.upload(
                        image,
                        public_id=f"test/image/{uuid.uuid4()}",  # Use your asset folder path
                        folder="test/image",  # Your configured asset folder
                        resource_type="auto",
                        upload_preset="inbrief_app"  # Your upload preset
                    )
                    # Get the secure URL from Cloudinary
                    cloudinary_url = result['secure_url']
                    image_urls.append(cloudinary_url)
                    logger.info(f"Image uploaded to Cloudinary: {cloudinary_url}")
                except Exception as e:
                    logger.error(f"Error uploading image to Cloudinary: {e}")
                    return jsonify({'error': 'Failed to upload image'}), 500
                
    post_id = generate_post_id()
    ist = pytz.timezone('Asia/Kolkata')
    date_str = datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')
    news_item = {
        'id': post_id,
        'headline': headline,
        'description': description,
        'image_urls': image_urls,
        'date': date_str,
        'category': category,  # Only stored in backend, not sent to mobile app
        'author': session.get('employee_name')
    }
    news_posts.insert(0, news_item)
    return jsonify({'success': True, 'item': news_item}), 201

# Edit a post by id
@app.route('/api/news/edit/<post_id>', methods=['POST'])
@login_required
def edit_news(post_id):
    for post in news_posts:
        if post['id'] == post_id:
            # Check if post is older than 2 hours
            if not is_post_editable(post['date']):
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
                
            post['headline'] = headline
            post['description'] = description
            if category:
                post['category'] = category
                
            if images and len(images) > 0:
                image_urls = []
                for image in images:
                    if image:
                        try:
                            # Upload to Cloudinary with your specific configuration
                            result = cloudinary.uploader.upload(
                                image,
                                public_id=f"test/image/{uuid.uuid4()}",  # Use your asset folder path
                                folder="test/image",  # Your configured asset folder
                                resource_type="auto",
                                upload_preset="inbrief_app"  # Your upload preset
                            )
                            # Get the secure URL from Cloudinary
                            cloudinary_url = result['secure_url']
                            image_urls.append(cloudinary_url)
                            logger.info(f"Image uploaded to Cloudinary: {cloudinary_url}")
                        except Exception as e:
                            logger.error(f"Error uploading image to Cloudinary: {e}")
                            return jsonify({'error': 'Failed to upload image'}), 500
                post['image_urls'] = image_urls
                
            return jsonify({'success': True, 'item': post}), 200
            
    return jsonify({'error': 'Post not found'}), 404

# Delete a post
@app.route('/api/news/delete/<post_id>', methods=['DELETE'])
@login_required
def delete_news(post_id):
    for i, post in enumerate(news_posts):
        if post['id'] == post_id:
            # Remove images from Cloudinary if present
            image_urls = post.get('image_urls', [])
            for url in image_urls:
                if url and 'cloudinary.com' in url:
                    try:
                        # Extract public_id from Cloudinary URL
                        # URL format: https://res.cloudinary.com/dttnc46ds/image/upload/v1234567890/test/image/uuid.jpg
                        parts = url.split('/')
                        if len(parts) >= 8:
                            public_id = '/'.join(parts[7:])  # Get the part after 'upload/'
                            # Remove file extension
                            public_id = public_id.rsplit('.', 1)[0]
                            # Delete from Cloudinary
                            result = cloudinary.uploader.destroy(public_id)
                            logger.info(f"Deleted image from Cloudinary: {public_id}")
                    except Exception as e:
                        logger.error(f"Error deleting image from Cloudinary: {e}")
            news_posts.pop(i)
            return jsonify({'success': True}), 200
    return jsonify({'error': 'Post not found'}), 404

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

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

# Get admin list
@app.route('/api/admin/list', methods=['GET'])
@login_required
def get_admin_list():
    try:
        return jsonify({'admins': list(ALLOWED_ADMIN_IDS)})
    except Exception as e:
        logger.error(f"Error getting admin list: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Remove admin
@app.route('/api/admin/remove', methods=['POST'])
@login_required
def remove_admin():
    data = request.get_json()
    emp_id = data.get('empId')

    if not emp_id:
        return jsonify({'error': 'Employee ID is required'}), 400

    try:
        # Verify the requesting user is an admin
        if session.get('employee_id') not in ALLOWED_ADMIN_IDS:
            return jsonify({'error': 'Unauthorized to remove admin access'}), 403

        # Prevent removing yourself
        if emp_id == session.get('employee_id'):
            return jsonify({'error': 'Cannot remove your own admin access'}), 400

        # Remove from ALLOWED_ADMIN_IDS
        if emp_id in ALLOWED_ADMIN_IDS:
            ALLOWED_ADMIN_IDS.remove(emp_id)
            logger.info(f"Admin access removed from Employee ID: {emp_id} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Employee is not an admin'}), 404

    except Exception as e:
        logger.error(f"Error removing admin: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Get port from environment variable for production deployment
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    # Use threaded=True for better handling of concurrent requests
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
