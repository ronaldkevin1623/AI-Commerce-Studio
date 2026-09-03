"""
GIVE THE DEMO STORE'S OWN PRODUCTS AN ILLUSTRATION — NOT A PHOTOGRAPH.

The store has no product photography. Search results already handle that
honestly with a labelled "No photo" tile, but merchant items are then
excluded from the recommendation row, which requires an image.

The tempting fix is a stock photo of a similar-looking cable. That would be
a picture of somebody else's product presented as this store's inventory,
which is exactly the kind of small lie this project refuses.

So each product gets a flat SVG built from what the record actually says:
its category, its name, its price. Deliberately iconographic — solid
ground, a line glyph, the name in text — so that at a glance, next to real
eBay photographs, nobody mistakes it for one. A gradient-and-blur "product
render" would have been prettier and would have crossed the line.

Every record is also stamped `image_kind: "generated_illustration"`, so the
system knows what it is holding and the UI can say so rather than leaving a
viewer to assume.

    python tools_generate_product_art.py            # preview
    python tools_generate_product_art.py --commit   # write
"""
import argparse
import base64
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# One simple line glyph per category the catalogue actually uses. Drawn as
# paths rather than emoji so it renders identically everywhere and carries
# no accidental platform styling.
GLYPHS = {
    "cables": "M18 30 h10 a10 10 0 0 1 0 20 h-8 a10 10 0 0 0 0 20 h10",
    "home office": "M14 54 h44 M22 54 V32 h28 v22 M30 32 v-8 h12 v8",
    "bags": "M16 34 h40 v34 a4 4 0 0 1-4 4 H20 a4 4 0 0 1-4-4 z M28 34 v-8 a8 8 0 0 1 16 0 v8",
    "computer accessories": "M12 30 h48 v28 H12 z M12 44 h48 M24 30 v28 M48 30 v28",
    "audio": "M20 52 v-8 a16 16 0 0 1 32 0 v8 M14 52 h10 v16 H14 z M48 52 h10 v16 H48 z",
}
DEFAULT_GLYPH = "M16 24 h40 v40 H16 z M16 40 h40"

# Muted, low-saturation grounds. Nothing that looks like studio lighting.
PALETTE = [
    ("#1F2933", "#7B8794"), ("#22303C", "#8AA4B8"), ("#2A2622", "#A79383"),
    ("#1E2A25", "#7FA694"), ("#2B2430", "#9C8AA6"), ("#2E2A22", "#B0A07C"),
]


def _wrap(text: str, per_line: int = 22) -> list:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > per_line:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines[:3]


def illustration(product: dict) -> str:
    """A flat SVG for one product, as a data URI."""
    name = product.get("name") or "Product"
    category = (product.get("category") or "").lower()
    glyph = GLYPHS.get(category, DEFAULT_GLYPH)
    ground, ink = PALETTE[sum(ord(c) for c in product["id"]) % len(PALETTE)]

    lines = _wrap(name)
    text = "".join(
        f'<text x="36" y="{150 + i * 19}" fill="{ink}" font-size="15" '
        f'font-family="Segoe UI, system-ui, sans-serif" font-weight="500">'
        f'{line.replace("&", "&amp;").replace("<", "&lt;")}</text>'
        for i, line in enumerate(lines))

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240" '
        f'viewBox="0 0 320 240">'
        f'<rect width="320" height="240" fill="{ground}"/>'
        f'<g transform="translate(128 34)" fill="none" stroke="{ink}" '
        f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" '
        f'opacity="0.85"><path d="{glyph}"/></g>'
        f'{text}'
        # Said on the tile itself, not only in a database field. A viewer
        # should not have to inspect anything to know this is not a photo.
        f'<text x="36" y="215" fill="{ink}" font-size="10.5" opacity="0.62" '
        f'font-family="Segoe UI, system-ui, sans-serif" letter-spacing="0.6">'
        f'ILLUSTRATION &#183; NOT A PRODUCT PHOTO</text>'
        f'</svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    from app.merchant import store
    products = store.list_products()
    if not products:
        print("\nNo products in the catalogue.\n")
        return 1

    print("\n" + "=" * 68)
    print(f"  {'WOULD WRITE' if not args.commit else 'WRITING'} illustrations "
          f"for {len(products)} product(s)")
    print("=" * 68)

    for product in products:
        uri = illustration(product)
        size_kb = len(uri) / 1024
        if len(uri) > store.MAX_IMAGE_CHARS:
            print(f"  [SKIP] {product['name'][:40]} — {size_kb:.1f}KB is over "
                  f"the {store.MAX_IMAGE_CHARS // 1024}KB record cap")
            continue
        print(f"  {product['name'][:44]:<46} {product.get('category', ''):<22} "
              f"{size_kb:>5.1f}KB")
        if args.commit:
            store.db.collection(store.PRODUCTS).document(product["id"]).update({
                "image": uri,
                # So nothing downstream has to guess what this is.
                "image_kind": "generated_illustration",
            })

    print("=" * 68)
    if not args.commit:
        print("  Preview only. Nothing written. Re-run with --commit.")
    else:
        print("  Written. Each record carries image_kind=generated_illustration.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
