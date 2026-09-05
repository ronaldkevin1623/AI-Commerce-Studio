import { useEffect, useState } from "react";
import {
  collection, getDocs, onSnapshot, orderBy, query, limit,
} from "firebase/firestore";
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
  const [error, setError] = useState(null);

  useEffect(() => {
    const q = query(
      collection(db, "decisions"),
      orderBy("timestamp", "desc"),
      limit(maxEntries)
    );

    const unsubscribe = onSnapshot(
      q,
      (snapshot) => {
        const rows = snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
        setDecisions(rows);
        setError(null);
        setLoading(false);
      },
      // Without this the subscription fails silently and the page waits on a
      // connection that is never coming. An audit trail that cannot reach its
      // log has to say so rather than imply it is still loading.
      (err) => {
        setError(err?.message || String(err));
        setLoading(false);
      }
    );

    return () => unsubscribe();
  }, [maxEntries]);

  return { decisions, loading, error };
}


/**
 * EVERY decision, once, for export.
 *
 * The live subscription above is deliberately capped: a page that streams
 * the whole log would get slower every day it runs, and nobody reads the
 * four-hundredth row on screen.
 *
 * An export is a different promise. A button labelled "Export log" on a
 * system whose central claim is a complete audit trail has to hand over
 * the complete audit trail — it was writing the fifty rows the page
 * happened to be holding, out of hundreds, with nothing in the file
 * saying so. Someone reconciling money against that CSV would have
 * concluded the missing actions never happened.
 *
 * So this reads the collection once, unlimited, at the moment the button
 * is pressed. It is not a subscription and holds nothing open.
 */
export async function fetchAllDecisions() {
  const snapshot = await getDocs(
    query(collection(db, "decisions"), orderBy("timestamp", "desc"))
  );
  return snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
}
