import os
import json
import io
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth
from PIL import Image

# --- Flask App ইনিশিয়ালাইজেশন ---
app = Flask(__name__)
# CORS(app) লোকাল ডেভেলপমেন্টের জন্য প্রয়োজন হতে পারে, Vercel এ এটি না দিলেও চলে
CORS(app, resources={r"/api/*": {"origins": "*"}}) 

# --- Firebase Admin SDK ইনিশিয়ালাইজেশন ---
try:
    # Vercel এনভায়রনমেন্ট ভ্যারিয়েবল থেকে Firebase কনফিগ লোড
    firebase_config_str = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY_JSON')
    if firebase_config_str:
        cred_json = json.loads(firebase_config_str)
        cred = credentials.Certificate(cred_json)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
    else:
        # লোকাল ডেভেলপমেন্টের জন্য (টার্মিনাল ছাড়া কাজ করলে এই অংশটি এড়িয়ে যেতে পারেন)
        print("Warning: FIREBASE_SERVICE_ACCOUNT_KEY_JSON not found. Using local file.")
        if not firebase_admin._apps:
            cred = credentials.Certificate('path/to/your/serviceAccountKey.json')
            firebase_admin.initialize_app(cred)
except Exception as e:
    print(f"Firebase Initialization Error: {e}")

db = firestore.client()

# --- Helper Functions (সহায়ক ফাংশন) ---

def verify_firebase_token(request):
    """Firebase ID টোকেন ভেরিফাই করে এবং ইউজার ডেটা রিটার্ন করে"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None
        id_token = auth_header.split('Bearer ').pop()
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None

def is_admin(user_id):
    """Firestore থেকে চেক করে দেখে ইউজার অ্যাডমিন কিনা"""
    try:
        user_doc = db.collection('users').document(user_id).get()
        if user_doc.exists and user_doc.to_dict().get('role') == 'admin':
            return True
        return False
    except Exception as e:
        print(f"Admin check failed: {e}")
        return False

# ===============================================
# PUBLIC ROUTES (যে কেউ অ্যাক্সেস করতে পারবে)
# ===============================================

@app.route('/api/images', methods=['GET'])
def get_images():
    """সম্প্রতি অনুমোদিত ছবিগুলোর একটি তালিকা দেয়"""
    try:
        limit = int(request.args.get('limit', 20))
        query = db.collection('images').where('approved', '==', True).order_by('createdAt', direction=firestore.Query.DESCENDING).limit(limit).stream()
        
        images = []
        for doc in query:
            img_data = doc.to_dict()
            img_data['id'] = doc.id
            images.append(img_data)
            
        return jsonify(images), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/images/<slug>', methods=['GET'])
def get_image_by_slug(slug):
    """একটি নির্দিষ্ট ছবির বিস্তারিত তথ্য তার slug দিয়ে খুঁজে বের করে"""
    try:
        query = db.collection('images').where('slug', '==', slug).where('approved', '==', True).limit(1).stream()
        image = next((doc.to_dict() for doc in query), None)
        
        if image:
            return jsonify(image), 200
        return jsonify({"error": "Image not found or not approved"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/search', methods=['GET'])
def search_images():
    """কীওয়ার্ড দিয়ে ছবি খোঁজার জন্য"""
    try:
        query_term = request.args.get('q', '').lower().strip()
        if not query_term:
            return jsonify({"error": "A search term 'q' is required."}), 400

        # ট্যাগ দিয়ে সার্চ
        query = db.collection('images').where('approved', '==', True).where('tags', 'array_contains', query_term).stream()
        
        results = []
        for doc in query:
            img_data = doc.to_dict()
            img_data['id'] = doc.id
            results.append(img_data)
        
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ====================================================
# AUTHENTICATED ROUTES (শুধু লগইন করা ইউজারদের জন্য)
# ====================================================

@app.route('/api/upload', methods=['POST'])
def upload_image():
    """লগইন করা ইউজারদের জন্য ছবি আপলোড"""
    user = verify_firebase_token(request)
    if not user:
        return jsonify({"error": "Unauthorized user"}), 401

    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    title = request.form.get('title')
    tags_str = request.form.get('tags', '')
    if not title or not tags_str:
        return jsonify({"error": "Title and tags are required"}), 400

    image_file = request.files['image']
    imgbb_api_key = os.environ.get('IMGBB_API_KEY')
    if not imgbb_api_key:
        return jsonify({"error": "Server error: ImgBB API key not configured"}), 500

    # ছবি রিসাইজ ও কমপ্রেস
    try:
        img = Image.open(image_file.stream)
        img.thumbnail((1920, 1080)) # সর্বোচ্চ রেজোলিউশন
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        buffer.seek(0)
    except Exception as e:
        return jsonify({"error": f"Image processing failed: {e}"}), 400
    
    # ImgBB-তে আপলোড
    upload_url = "https://api.imgbb.com/1/upload"
    payload = {"key": imgbb_api_key}
    response = requests.post(upload_url, data=payload, files={'image': buffer})
    
    if response.status_code != 200:
        return jsonify({"error": "Failed to upload to image host"}), 500

    result = response.json()['data']
    
    # Firestore-এ ডেটা সেভ
    slug = title.lower().replace(' ', '-') + '-' + os.urandom(3).hex()
    tags = [tag.strip().lower() for tag in tags_str.split(',')]
    
    image_data = {
        'title': title,
        'slug': slug,
        'tags': tags,
        'imageUrl': result['url'],
        'thumbUrl': result['thumb']['url'],
        'deleteUrl': result['delete_url'], # ছবি ডিলিট করার জন্য এটি সেভ করা গুরুত্বপূর্ণ
        'authorId': user['uid'],
        'authorName': user.get('name', user.get('email', 'Anonymous')),
        'approved': False,
        'downloads': 0,
        'createdAt': firestore.SERVER_TIMESTAMP
    }
    
    db.collection('images').add(image_data)
    return jsonify({"success": True, "message": "Image uploaded, pending approval."}), 201

@app.route('/api/my-images', methods=['GET'])
def get_my_images():
    """লগইন করা ইউজারের নিজের আপলোড করা সব ছবি দেখায়"""
    user = verify_firebase_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        query = db.collection('images').where('authorId', '==', user['uid']).order_by('createdAt', direction=firestore.Query.DESCENDING).stream()
        images = []
        for doc in query:
            img_data = doc.to_dict()
            img_data['id'] = doc.id
            images.append(img_data)
            
        return jsonify(images), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===============================================
# ADMIN ROUTES (শুধু অ্যাডমিনদের জন্য)
# ===============================================

@app.route('/api/admin/pending-images', methods=['GET'])
def get_pending_images():
    """অনুমোদনের জন্য অপেক্ষমাণ ছবিগুলো দেখায়"""
    user = verify_firebase_token(request)
    if not user or not is_admin(user['uid']):
        return jsonify({"error": "Forbidden: Admins only"}), 403
    
    query = db.collection('images').where('approved', '==', False).order_by('createdAt').stream()
    images = []
    for doc in query:
        img_data = doc.to_dict()
        img_data['id'] = doc.id
        images.append(img_data)
        
    return jsonify(images), 200

@app.route('/api/admin/approve-image', methods=['POST'])
def approve_image():
    """একটি ছবি অনুমোদন করে"""
    user = verify_firebase_token(request)
    if not user or not is_admin(user['uid']):
        return jsonify({"error": "Forbidden: Admins only"}), 403
        
    image_id = request.json.get('imageId')
    if not image_id:
        return jsonify({"error": "Image ID is required"}), 400
        
    db.collection('images').document(image_id).update({'approved': True})
    return jsonify({"success": True, "message": "Image approved successfully."}), 200

@app.route('/api/admin/reject-image', methods=['POST'])
def reject_image():
    """একটি ছবি প্রত্যাখ্যান করে এবং মুছে ফেলে"""
    user = verify_firebase_token(request)
    if not user or not is_admin(user['uid']):
        return jsonify({"error": "Forbidden: Admins only"}), 403
    
    image_id = request.json.get('imageId')
    if not image_id:
        return jsonify({"error": "Image ID is required"}), 400
    
    # ImgBB থেকে ছবিটি মুছে ফেলার চেষ্টা করা (ঐচ্ছিক, কারণ ImgBB এর জন্য সরাসরি API নাও থাকতে পারে)
    # doc_ref = db.collection('images').document(image_id)
    # doc = doc_ref.get()
    # if doc.exists:
    #     delete_url = doc.to_dict().get('deleteUrl')
    #     if delete_url:
    #         # requests.delete(delete_url) # এই অংশটি ImgBB ডকুমেন্টেশন অনুযায়ী করতে হবে

    db.collection('images').document(image_id).delete()
    return jsonify({"success": True, "message": "Image rejected and deleted successfully."}), 200

# এই রাউটটি Vercel-এর জন্য আবশ্যক নয়, কিন্তু লোকাল ডেভেলপমেন্টের জন্য রুট URL এ কিছু দেখাতে সাহায্য করে
@app.route('/api', methods=['GET'])
def api_root():
    return "<h1>Stock Photo API is running!</h1>"
