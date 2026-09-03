"""
Show the Razorpay order behind the most recent trip stay, and its notes.

For the demo: after clicking Pay on an itinerary, this reads the order back
FROM RAZORPAY — not from this app's database — and prints the hotel record
id Razorpay is holding. That is the point being made on stage: the link
between the itinerary and the money survives outside our own storage.
"""
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()
import razorpay

client = razorpay.Client(auth=(os.getenv("RAZORPAY_KEY_ID"),
                               os.getenv("RAZORPAY_KEY_SECRET")))
orders = client.order.all({"count": 20}).get("items", [])
trip = next((o for o in orders if (o.get("notes") or {}).get("hotel_record_id")), None)

if not trip:
    print("\nNo trip stay order found in the last 20 Razorpay orders.\n")
    raise SystemExit(1)

notes = trip["notes"]
print("\n" + "=" * 66)
print("  Read back from the Razorpay API, not from our database")
print("=" * 66)
print(f"  order          {trip['id']}")
print(f"  amount         Rs{trip['amount'] / 100:,.2f}   status={trip['status']}")
print("  notes Razorpay is holding:")
for key in ("sector", "leg", "hotel_record_id", "hotel_name", "city",
            "nights", "nightly_paise", "tax_paise"):
    if key in notes:
        print(f"    {key:16} {notes[key]}")
print("=" * 66)

# Re-derive the amount from the dataset row alone.
from app.sectors import trip_data
row = next((h for h in trip_data.hotels()
            if h["record_id"] == notes["hotel_record_id"]), None)
if row:
    derived = (row["price_paise"] + row["tax_paise"]) * int(notes.get("nights") or 1)
    print(f"  Re-derived from the dataset row alone: Rs{derived / 100:,.2f}")
    print(f"  Matches what Razorpay holds          : {derived == trip['amount']}")
    print("=" * 66 + "\n")
