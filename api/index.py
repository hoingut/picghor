import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth
from PIL import Image
import io

# --- Firebase Admin SDK ইনিশিয়ালাইজেশন ---
# Vercel এনভায়রনমেন্ট ভ্যারিয়েবল থেকে Firebase কনফিগ লোড করুন
# এটিকে একটি স্ট্রিং থেকে ডিকশনারিতে রূপান্তর করতে হবে
import json
firebase_config_str = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY_JSON')
if firebase_config_str:
    cred_json = json.loads(firebase_config_str)
    cred = credentials.Certificate(cred_json)
    firebase_admin.initialize_app(cred)
else:
    # লোকাল ডেভেলপমেন্টের জন্য serviceAccountKey.json ফাইল ব্যবহার করুন
    if not firebase_admin._apps:
        cred = credentials.Certificate('path/to/your/serviceAccountKey.json') # আপনার ফাইলের পাথ দিন
        firebase_admin.initialize_app(cred)

db = firestore.client()
app = Flask(__name__)
CORS(app) # সকল ডোমেইন থেকে রিকোয়েস্ট অ্যালাও করার জন্য

# --- Middleware: Firebase টোকেন ভেরিফাই করার জন্য ---
def check_auth(request):
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None
        id_token = auth_header.split(' ').pop()
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        print(f"Auth error: {e}")
        return None

# --- API Endpoints ---

@app.route('/api/images', methods=['GET'])
def get_images():
    # এখানে trending, recent, featured ছবি ফিল্টার করার লজিক যোগ করা যেতে পারে
    query = db.collection('images').where('approved', '==', True).limit(20).stream()
    images = [doc.to_dict() for doc in query]
    return jsonify(images), 200

@app.route('/api/images/<slug>', methods=['GET'])
def get_image_by_slug(slug):
    query = db.collection('images').where('slug', '==', slug).limit(1).stream()
    image = next((doc.to_dict() for doc in query), None)
    if image:
        return jsonify(image), 200
    return jsonify({"error": "Image not found"}), 404

@app.route('/api/upload', methods=['POST'])
def upload_image():
    user = check_auth(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    image_file = request.files['image']
    title = request.form.get('title')
    tags = request.form.get('tags', '').split(',')
    
    # --- ImgBB তে ছবি আপলোড ---
    imgbb_api_key = os.environ.get('IMGBB_API_KEY')
    if not imgbb_api_key:
        return jsonify({"error": "ImgBB API key not configured"}), 500

    # ছবি কম্প্রেশন এবং থাম্বনেইল তৈরি (ঐচ্ছিক)
    img = Image.open(image_file.stream)
    img.thumbnail((1920, 1080)) # রিসাইজ
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85) # কমপ্রেস
    buffer.seek(0)

    upload_url = "https://api.imgbb.com/1/upload"
    payload = {
        "key": imgbb_api_key,
    }
    files = {'image': buffer}
    response = requests.post(upload_url, data=payload, files=files)
    
    if response.status_code == 200:
        result = response.json()
        image_url = result['data']['url']
        thumb_url = result['data']['thumb']['url']
        
        # --- Firestore এ ছবির মেটাডেটা সেভ করা ---
        slug = title.lower().replace(' ', '-') + '-' + os.urandom(4).hex()
        image_data = {
            'title': title,
            'tags': [tag.strip() for tag in tags],
            'imageUrl': image_url,
            'thumbUrl': thumb_url,
            'slug': slug,
            'authorId': user['uid'],
            'authorName': user.get('name', 'Anonymous'),
            'approved': False, # অ্যাডমিন অ্যাপ্রুভালের জন্য পেন্ডিং
            'downloads': 0,
            'createdAt': firestore.SERVER_TIMESTAMP
        }
        db.collection('images').add(image_data)
        return jsonify({"success": True, "message": "Image uploaded successfully, pending approval."}), 201
    else:
        return jsonify({"error": "Failed to upload to ImgBB"}), 500

# --- অ্যাডমিন এন্ডপয়েন্ট (উদাহরণ) ---
@app.route('/api/admin/approve', methods=['POST'])
def approve_image():
    user = check_auth(request)
    # অ্যাডমিন কিনা তা চেক করুন
    if not user or not user.get('admin'):
        return jsonify({"error": "Forbidden: Admins only"}), 403

    image_id = request.json.get('imageId')
    if not image_id:
        return jsonify({"error": "Image ID required"}), 400

    db.collection('images').document(image_id).update({'approved': True})
    return jsonify({"success": True}), 200

# Flask অ্যাপটি Vercel-এর জন্য এক্সপোর্ট করা
# এই অংশটি লোকাল ডেভেলপমেন্টের জন্য প্রয়োজন
if __name__ == '__main__':
    app.run(debug=True)
