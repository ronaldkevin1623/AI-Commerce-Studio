import { initializeApp } from "firebase/app";
import { connectFirestoreEmulator, getFirestore } from "firebase/firestore";

import { API_BASE } from "../config";

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

// Which datastore this page ended up on, for the UI to state plainly.
export const datastore = { binding: "", ready: false, error: "" };

/**
 * POINT THE BROWSER AT THE SAME DATASTORE AS THE BACKEND.
 *
 * Two pages — Audit trail and Failure recovery — subscribe to Firestore
 * DIRECTLY from the browser rather than going through the API, because
 * they want live updates as the agent writes decisions. That is the right
 * design for them and completely wrong by default: this client was
 * configured for the production project, so with the backend running on
 * the local emulator those two pages watched a different database and
 * showed nothing the agent did.
 *
 * The backend is asked which store it is on rather than a second
 * environment variable being introduced here. One source of truth was the
 * whole point of moving the datastore choice to launch time; adding a
 * VITE_ flag would recreate the drift it removed.
 *
 * Must run before anything reads `db` — Firestore refuses to switch to an
 * emulator once the client has started operating.
 */
export async function connectDatastore() {
  try {
    const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    const health = await res.json();
    const binding = health?.datastore || "";
    datastore.binding = binding;

    if (binding.startsWith("emulator")) {
      // binding looks like "emulator:127.0.0.1:8085"
      const hostPort = binding.slice("emulator:".length) || "127.0.0.1:8085";
      const [host, port] = hostPort.split(":");
      connectFirestoreEmulator(db, host, Number(port) || 8085);
    }
    datastore.ready = true;
  } catch (err) {
    // Not fatal: every other page goes through the API and is unaffected.
    // The two live pages will say they could not determine the datastore
    // rather than quietly watching the wrong one.
    datastore.error = String(err);
    datastore.ready = false;
  }
}
