import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyD6QJh5dhol-NAWf3FJVCtDQVWSt5gAccA",
  authDomain: "cart-pilot-9a550.firebaseapp.com",
  projectId: "cart-pilot-9a550",
  storageBucket: "cart-pilot-9a550.firebasestorage.app",
  messagingSenderId: "412171364720",
  appId: "1:412171364720:web:1491eb5a5a6f3cad0507b5",
  measurementId: "G-T5N7709WSR",
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);