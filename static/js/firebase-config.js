// Firebase v9 Modular SDK
import { initializeApp } from "https://www.gstatic.com/firebasejs/9.6.1/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/9.6.1/firebase-auth.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/9.6.1/firebase-firestore.js";


// আপনার Firebase প্রজেক্টের কনফিগারেশন এখানে যুক্ত করুন
const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "YOUR_AUTH_DOMAIN",
  projectId: "YOUR_PROJECT_ID",
  storageBucket: "YOUR_STORAGE_BUCKET",
  messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
  appId: "YOUR_APP_ID"
};

// Firebase অ্যাপ ইনিশিয়ালাইজ করুন
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

// অন্য ফাইলে ব্যবহারের জন্য এক্সপোর্ট করুন
export { auth, db };
