import asyncio
import json
import os
import random
from typing import List, Dict, Any, Tuple

import pandas as pd

from google_maps_scraping import scrape_google_maps_reviews

INPUT_FILE = "place_links_spklu_jakarta.json"
STATE_FILE = "progress_state.json"

MASTER_JSON = "all_places_reviews.json"
MASTER_CSV = "all_places_reviews.csv"

PROFILE_PREFIX = "gmaps_profile_part"


def load_links(path: str) -> List[str]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("place_links.json must be a JSON array of URLs")

    # unique while keeping order
    seen = set()
    out = []
    for x in data:
        if isinstance(x, str) and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"next_index": 0}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict):
            return {"next_index": 0}
        if "next_index" not in state or not isinstance(state["next_index"], int):
            return {"next_index": 0}
        return state
    except Exception:
        return {"next_index": 0}


def save_state(next_index: int) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"next_index": next_index}, f, ensure_ascii=False, indent=2)


def load_master_json() -> List[Dict[str, Any]]:
    if not os.path.exists(MASTER_JSON):
        return []
    try:
        with open(MASTER_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_master_json(data: List[Dict[str, Any]]) -> None:
    with open(MASTER_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_master_csv() -> pd.DataFrame:
    if not os.path.exists(MASTER_CSV):
        return pd.DataFrame()
    try:
        return pd.read_csv(MASTER_CSV)
    except Exception:
        return pd.DataFrame()


def save_master_csv(df: pd.DataFrame) -> None:
    df.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")


def merge_master_json(existing: List[Dict[str, Any]], new_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate by place_url: keep existing if already present.
    If you want "latest overwrite", I can change it.
    """
    by_url = {}
    for item in existing:
        url = item.get("place_url")
        if url:
            by_url[url] = item

    for item in new_items:
        url = item.get("place_url")
        if url and url not in by_url:
            by_url[url] = item

    # stable order: existing first, then new
    out = []
    seen = set()
    for item in existing + new_items:
        url = item.get("place_url")
        if url and url in by_url and url not in seen:
            out.append(by_url[url])
            seen.add(url)
    return out


def merge_master_csv(existing_df: pd.DataFrame, new_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    new_df = pd.DataFrame(new_rows)
    if existing_df.empty:
        return new_df

    combined = pd.concat([existing_df, new_df], ignore_index=True)

    # Deduplicate reviews rows (same place_url + user_name + timestamp + text_review)
    key_cols = [c for c in ["place_url", "user_name", "timestamp", "text_review"] if c in combined.columns]
    if key_cols:
        combined = combined.drop_duplicates(subset=key_cols, keep="first")

    return combined


async def scrape_chunk(
    links: List[str],
    start_index: int,
    chunk_size: int,
    headless: bool,
    max_reviews_per_place: int,
    max_scrolls: int,
    profile_dir: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:

    end_index = min(start_index + chunk_size, len(links))
    target_links = links[start_index:end_index]

    chunk_results: List[Dict[str, Any]] = []
    chunk_rows: List[Dict[str, Any]] = []

    print(f"\nProfile folder: {profile_dir}")
    print(f"Scraping index {start_index} to {end_index - 1} ({len(target_links)} links)\n")

    for i, link in enumerate(target_links, start=1):
        global_i = start_index + i - 1
        print(f"===== [{i}/{len(target_links)}] (global {global_i}/{len(links)-1}) =====")
        print(f"Scraping: {link}")

        try:
            result = await scrape_google_maps_reviews(
                place_url=link,
                max_reviews=max_reviews_per_place,
                headless=headless,
                max_scrolls=max_scrolls,
                profile_dir=profile_dir,
            )

            print(f"✓ Done: {result.place_name} ({len(result.reviews)} reviews)")

            chunk_results.append({
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

            for r in result.reviews:
                chunk_rows.append({
                    "place_url": result.place_url,
                    "place_name": result.place_name,
                    "place_location": result.place_location,
                    "user_name": r.user_name,
                    "rating": r.rating,
                    "timestamp": r.timestamp,
                    "text_review": r.text_review,
                })

        except Exception as e:
            print(f"✗ Failed: {link}")
            print(f"  Error: {e}")

        # Save progress index after each place
        save_state(global_i + 1)

        await asyncio.sleep(random.uniform(12, 25))

    return chunk_results, chunk_rows, end_index


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk_size", type=int, default=10)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max_reviews", type=int, default=5000)
    parser.add_argument("--max_scrolls", type=int, default=250)
    parser.add_argument("--start_index", type=int, default=None)
    args = parser.parse_args()

    headless_mode = True
    if args.headed:
        headless_mode = False
    elif args.headless:
        headless_mode = True

    links = load_links(INPUT_FILE)
    state = load_state()
    next_index = state.get("next_index", 0)

    if args.start_index is not None:
        next_index = args.start_index

    if next_index >= len(links):
        print("All links already processed ✅")
        raise SystemExit(0)

    # pick profile per run using next_index (stable)
    run_no = (next_index // args.chunk_size) + 1
    profile_dir = f"{PROFILE_PREFIX}{run_no}"
    os.makedirs(profile_dir, exist_ok=True)

    chunk_results, chunk_rows, new_next_index = asyncio.run(
        scrape_chunk(
            links=links,
            start_index=next_index,
            chunk_size=args.chunk_size,
            headless=headless_mode,
            max_reviews_per_place=args.max_reviews,
            max_scrolls=args.max_scrolls,
            profile_dir=profile_dir,
        )
    )

    # Load master outputs
    master_json = load_master_json()
    master_csv = load_master_csv()

    # Merge (append + dedupe)
    merged_json = merge_master_json(master_json, chunk_results)
    merged_csv = merge_master_csv(master_csv, chunk_rows)

    # Save master outputs
    save_master_json(merged_json)
    save_master_csv(merged_csv)

    # Save state
    save_state(new_next_index)

    print(f"\nSaved master: {MASTER_JSON}")
    print(f"Saved master: {MASTER_CSV}")
    print(f"Progress saved: {STATE_FILE} next_index={new_next_index}")
    print(f"Next run will continue from index {new_next_index}")