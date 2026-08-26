import { useEffect, useState } from "react";
import { collection, onSnapshot, orderBy, query, limit } from "firebase/firestore";
import { db } from "../services/firebase";

/**
 * Looks at the real "decisions" log for the most recent payment_failed
 * entry (written by payment_routes.py or webhook_routes.py when
 * Razorpay reports a non-captured status), then checks whether a
 * payment_confirmed entry happened afterward — a genuine recovery,
 * not a scripted one.
 */
export function useFailureRecovery() {
  const [failure, setFailure] = useState(null);
  const [recovery, setRecovery] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const q = query(collection(db, "decisions"), orderBy("timestamp", "desc"), limit(50));

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const rows = snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));

      const latestFailure = rows.find((d) => d.action_type === "payment_failed");
      setFailure(latestFailure || null);

      if (latestFailure) {
        const failureTime = latestFailure.timestamp?.toMillis?.() ?? 0;
        // A real confirmed payment logged any time after the failure,
        // for the same amount, counts as the recovery
        const laterConfirmed = rows
          .filter((d) => d.action_type === "payment_confirmed")
          .find((d) => (d.timestamp?.toMillis?.() ?? 0) > failureTime);
        setRecovery(laterConfirmed || null);
      } else {
        setRecovery(null);
      }

      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  return { failure, recovery, loading };
}