import asyncio
import json
import os
from typing import List

import pandas as pd

# Import your existing scraper function + dataclass
from google_maps_scraping import scrape_google_maps_reviews


INPUT_FILE = "place_links.json"
OUTPUT_JSON = "all_places_reviews.json"
OUTPUT_CSV = "all_places_reviews.csv"


async def scrape_all_places(
    links: List[str],
    headless: bool = False,
    max_reviews_per_place: int = 5000,
):
    all_results = []
    all_rows = []

    for idx, link in enumerate(links, start=1):
        print(f"\n===== [{idx}/{len(links)}] Scraping: {link} =====")

        try:
            result = await scrape_google_maps_reviews(
                place_url=link,
                max_reviews=max_reviews_per_place,
                headless=headless,
                max_scrolls=250,
            )

            print(
                f"✓ Done: {result.place_name} "
                f"({len(result.reviews)} reviews)"
            )

            # Save structured JSON-style object
            all_results.append({
                "place_url": result.place_url,
                "place_name": result.place_name,
                "place_location": result.place_location,
                "reviews": [
                    {
                        "user_name": r.user_name,
                        "rating": r.rating,
                        "timestamp": r.timestamp,
                        "text_review": r.text_review,
                    }
                    for r in result.reviews
                ],
            })

            # Also flatten for CSV
            for r in result.reviews:
                all_rows.append({
                    "place_url": result.place_url,
                    "place_name": result.place_name,
                    "place_location": result.place_location,
                    "user_name": r.user_name,
                    "rating": r.rating,
                    "timestamp": r.timestamp,
                    "text_review": r.text_review,
                })

        except Exception as e:
            print(f"✗ Failed on {link}")
            print(f"  Error: {e}")

        # Small delay between places to reduce throttling
        await asyncio.sleep(2)

    return all_results, all_rows


def save_results(all_results, all_rows):
    # Save JSON (nested)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # Save CSV (flat)
    df = pd.DataFrame(all_rows)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print(f"\nSaved JSON: {OUTPUT_JSON}")
    print(f"Saved CSV : {OUTPUT_CSV}")


if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"{INPUT_FILE} not found")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        links = json.load(f)

    print(f"Total links to scrape: {len(links)}")

    all_results, all_rows = asyncio.run(
        scrape_all_places(
            links=links,
            headless=False,  # set True if already logged-in persistent profile
            max_reviews_per_place=5000,
        )
    )

    save_results(all_results, all_rows)