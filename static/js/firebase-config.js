// Firebase v9 Modular SDK
import { initializeApp } from "https://www.gstatic.com/firebasejs/9.6.1/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/9.6.1/firebase-auth.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/9.6.1/firebase-firestore.js";


  // Your web app's Firebase configuration
  const firebaseConfig = {
    apiKey: "AIzaSyBdOVGQ1y79k9ojVYvbMnjU0M-ZQMqvj0w",
    authDomain: "picghor-345a1.firebaseapp.com",
    projectId: "picghor-345a1",
    storageBucket: "picghor-345a1.firebasestorage.app",
    messagingSenderId: "397866625070",
    appId: "1:397866625070:web:0906db7bd3e35a1fffd7bf"
  };



// Firebase অ্যাপ ইনিশিয়ালাইজ করুন
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

// অন্য ফাইলে ব্যবহারের জন্য এক্সপোর্ট করুন
export { auth, db };
