"""
THE PRODUCTS SECTOR — A DESCRIPTION OF WHAT ALREADY RUNS.

This file adds no behaviour. Everything a product search does is already
in app/routes/agent_routes.py and app/engines/, and it keeps doing it
exactly as before: same venues, same screens, same ranking, same gate.
What was implicit — "this application sells things" — is now written down
so a second sector can exist beside it without either becoming a special
case in the core.

`/deal` and `/premium` move here. They were global slash commands that
only ever made sense for products; now they are products templates, which
is what they always were. They still insert the same text and still run
the same pipeline. Nothing about them was renamed or dropped.

The adapters list points at the existing GLOBAL venue registry, and that
is correct only for this sector: eBay, the UCP store and retail media are
where products come from, and they were the whole world before sectors
existed. Trip registers its own providers privately and must never appear
here — a flight in a search for earbuds would mean the boundary leaked.
"""
import re

from app.sectors.base import Criterion, IntentField, Template


class ProductsSector:
    """Buying a thing. The behaviour this application already had."""

    sector_id = "products"
    name = "Products"
    icon = "shopping"
    description = "Find and buy a specific item across marketplaces and shops"
    can_transact = True

    def intent_schema(self):
        # Only the phrase is required. A product search with nothing but
        # "wireless earbuds" is a perfectly good search — which is exactly
        # what makes trip different, where a missing destination means
        # there is no search to run at all.
        return [
            IntentField("query", "text", required=True,
                        prompt="What are you looking for?",
                        example="wireless earbuds"),
            IntentField("max_price_paise", "money",
                        prompt="Any budget?", example="under ₹2000"),
            IntentField("condition", "enum",
                        prompt="New only, or is used fine?", example="new"),
            IntentField("priority", "enum",
                        prompt="Price, rating, or delivery speed?",
                        example="best value"),
        ]

    def adapters(self):
        # The existing global venue registry, unchanged.
        from app.adapters import registry
        return registry.adapters()

    def evaluation_criteria(self):
        # These mirror what quality.value_key and precision.preference_key
        # actually weigh today. Written as data so the UI can show the
        # agent's reasoning without anyone reading the ranking code.
        return [
            Criterion("quality", 0.40, "higher_is_better",
                      "Reviews and seller record, shrunk toward the mean "
                      "so a lone 5-star does not beat a well-reviewed rival"),
            Criterion("price", 0.30, "lower_is_better",
                      "Separates listings of similar quality, and only then"),
            Criterion("availability", 0.20, "higher_is_better",
                      "In stock and actually buyable"),
            Criterion("trust", 0.10, "higher_is_better",
                      "Price outliers and thin sellers are dropped, not scored"),
        ]

    def templates(self):
        # Moved verbatim from the global TEMPLATES array in PromptBar.
        return [
            Template("earbuds", "/earbuds", "wireless earbuds under ₹2000, fast delivery",
                     "wireless earbuds under ₹2000, fast delivery"),
            Template("deal", "/deal", "earbuds under ₹3000 with the best discount",
                     "earbuds under ₹3000 with the best discount"),
            Template("premium", "/premium", "highest rated earbuds under ₹7000",
                     "highest rated earbuds under ₹7000"),
        ]

    # Words that mean someone is shopping for an object. Kept narrow on
    # purpose: this scores its own claim and must not try to be a general
    # classifier, or it becomes the central map of every sector's
    # vocabulary that the registry exists to avoid.
    _GOODS = re.compile(
        r"\b(buy|order|cheap|cheapest|discount|deal|under|below|rated|review|"
        r"warranty|delivery|shipping|stock|brand|model|earbuds?|headphones?|"
        r"phone|laptop|keyboard|mouse|cable|charger|watch|shoes?|bottle|"
        r"speaker|monitor|camera|tv|refill|pack)\b", re.I)
    _MONEY = re.compile(r"(₹|rs\.?|inr)\s*\d|under\s+\d|\bbelow\s+\d", re.I)

    def classify(self, text: str) -> float:
        blob = (text or "").lower()
        if not blob.strip():
            return 0.0
        score = 0.0
        hits = len(set(self._GOODS.findall(blob)))
        score += min(0.6, hits * 0.22)
        if self._MONEY.search(blob):
            score += 0.2
        # A bare noun phrase with no travel vocabulary is far more likely a
        # product than anything else, so short unclaimed text leans here —
        # but weakly, so a real trip request still outranks it.
        if len(blob.split()) <= 6 and hits:
            score += 0.15
        return min(1.0, score)
