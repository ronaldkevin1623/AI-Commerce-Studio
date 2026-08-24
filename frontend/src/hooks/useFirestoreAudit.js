import { useEffect, useState } from "react";
import { collection, onSnapshot, orderBy, query, limit } from "firebase/firestore";
import { db } from "../services/firebase";

/**
 * Subscribes to the "decisions" collection in real time.
 * Every write your backend makes via log_decision() appears here
 * instantly — this is what makes the Audit Trail page "live"
 * without any manual refresh or polling.
 */
export function useFirestoreAudit(maxEntries = 50) {
  const [decisions, setDecisions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const q = query(
      collection(db, "decisions"),
      orderBy("timestamp", "desc"),
      limit(maxEntries)
    );

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const rows = snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
      setDecisions(rows);
      setLoading(false);
    });

    return () => unsubscribe();
  }, [maxEntries]);

  return { decisions, loading };
}