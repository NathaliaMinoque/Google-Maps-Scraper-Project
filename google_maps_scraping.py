"""
google_maps_scraping.py

Scrape Google Maps place reviews (public view) using Playwright.

Outputs:
- place_name
- place_location (address text)
- reviews: user_name, rating, timestamp, text_review

Usage:
  pip install playwright pandas
  playwright install chromium

  python google_maps_scraping.py --url "https://www.google.com/maps/place/..." --headed
  python google_maps_scraping.py --url "https://www.google.com/maps/place/..." --headless

Notes:
- Google Maps is dynamic and may show consent/login/captcha. This script:
  * avoids networkidle waits
  * attempts to close "Login untuk menulis ulasan" popup by clicking "Batal"
  * opens the review panel (Reviews/Ulasan)
  * scrolls the review feed container
"""

import asyncio
import json
import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# -----------------------------
# Data models
# -----------------------------
@dataclass
class Review:
    user_name: str
    rating: Optional[float]
    timestamp: str
    text_review: str


@dataclass
class PlaceReviews:
    place_url: str
    place_name: str
    place_location: str
    reviews: List[Review]


# -----------------------------
# Helpers
# -----------------------------
def _clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _parse_rating_from_aria(aria: str) -> Optional[float]:
    """
    Examples:
      "5 stars"
      "Rated 4.0 out of 5"
      "5 bintang"
    """
    if not aria:
        return None
    m = re.search(r"([0-5](?:\.\d)?)", aria)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


async def _maybe_accept_consent(page) -> None:
    """
    Best-effort: accept cookie/consent dialogs.
    This varies heavily by region and language.
    """
    candidates = [
        ("button", "Accept all"),
        ("button", "I agree"),
        ("button", "Accept"),
        ("button", "Setuju"),
        ("button", "Terima semua"),
        ("button", "Terima"),
    ]

    for role, name in candidates:
        try:
            btn = page.get_by_role(role, name=name)
            if await btn.count() > 0:
                await btn.first.click(timeout=2000)
                await page.wait_for_timeout(800)
                return
        except Exception:
            pass

    # Generic substring match
    try:
        btn = page.get_by_role("button", name=re.compile(r"accept|agree|setuju|terima", re.I))
        if await btn.count() > 0:
            await btn.first.click(timeout=2000)
            await page.wait_for_timeout(800)
            return
    except Exception:
        pass


async def _close_login_popup(page) -> None:
    """
    Closes the popup like:
      "Login dengan Akun Google untuk menulis ulasan"
    by clicking "Batal" / "Cancel" if present.
    """
    try:
        popup = page.locator("text=/Login dengan Akun Google/i")
        if await popup.count() == 0:
            popup = page.locator("text=/Sign in/i")

        if await popup.count() > 0:
            batal = page.get_by_role("button", name=re.compile(r"batal|cancel", re.I))
            if await batal.count() > 0:
                await batal.first.click(timeout=3000)
                await page.wait_for_timeout(800)
    except Exception:
        pass


async def _get_place_identity(page) -> Dict[str, str]:
    """
    Extract place name + address/location.
    """
    place_name = ""
    for sel in ["h1.DUwDvf", "h1[class*='DUwDvf']", "h1"]:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                place_name = _clean_text(await el.inner_text())
                if place_name:
                    break
        except Exception:
            pass

    place_location = ""
    for sel in [
        "button[data-item-id='address'] .Io6YTe",
        "[data-item-id='address'] .Io6YTe",
        "button[data-item-id='address']",
    ]:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                place_location = _clean_text(await el.inner_text())
                if place_location:
                    break
        except Exception:
            pass

    return {"place_name": place_name, "place_location": place_location}

def _review_cards_locator(page):
    # Try the common card first
    cards = page.locator("div.jftiEf")
    # If none, fallback to review-id based cards
    # (many builds include this)
    return cards if cards else page.locator("div[data-review-id]")

async def _get_cards_locator(page):
    cards = page.locator("div.jftiEf")
    if await cards.count() > 0:
        return cards
    return page.locator("div[data-review-id]")

async def _open_reviews_panel(page) -> None:
    await _close_login_popup(page)

    # Try several ways to click the "Ulasan" tab in Indonesian UI
    click_candidates = [
        lambda: page.get_by_role("tab", name=re.compile(r"^Ulasan$|^Reviews$", re.I)).first,
        lambda: page.locator("div[role='tablist']").locator("text=Ulasan").first,
        lambda: page.locator("text=Ulasan").first,
        lambda: page.locator("text=Reviews").first,
    ]

    clicked = False
    for get_target in click_candidates:
        try:
            target = get_target()
            if await target.count() > 0:
                await target.click(timeout=15000)
                await page.wait_for_timeout(1500)
                clicked = True
                break
        except Exception:
            pass

    await _close_login_popup(page)

    # If not clicked, we still try to proceed, but we must verify.
    # Verification: in reviews view, we usually see sorting/filter UI OR star rating items.
    await page.wait_for_timeout(1000)

async def _reviews_visible(page) -> bool:
    # Common container when reviews are open
    if await page.locator("div[role='feed']").count() > 0:
        return True

    # In reviews list, there are multiple star elements with aria-label
    stars = page.locator("span[role='img'][aria-label*='bintang' i], span[role='img'][aria-label*='stars' i]")
    if await stars.count() >= 3:  # multiple reviews => multiple stars
        return True

    # Sometimes there is "Urutkan" / "Sort" button in reviews panel
    if await page.locator("text=/Urutkan|Sort/i").count() > 0:
        return True

    return False

async def _scroll_reviews_until_done(page, pause_ms: int = 900, max_rounds: int = 200) -> None:
    # Verify we're really in Reviews
    if not await _reviews_visible(page):
        await page.screenshot(path="debug_not_in_reviews.png", full_page=True)
        raise RuntimeError(
            "Still not in Reviews/Ulasan view. Saved debug_not_in_reviews.png. "
            "Clicking Ulasan likely failed or limited view is blocking."
        )

    # Find scroll container
    scrollbox = page.locator("div[role='feed']").first
    if await scrollbox.count() == 0:
        scrollbox = page.locator("div.m6QErb.DxyBCb.kA9KIf.dS8AEf").first
    if await scrollbox.count() == 0:
        scrollbox = page.locator("div.m6QErb.DxyBCb.kA9KIf").first

    if await scrollbox.count() == 0:
        return

    # Use stars count as progress signal (more reliable than jftiEf)
    stars = page.locator("span[role='img'][aria-label*='bintang' i], span[role='img'][aria-label*='stars' i]")

    last = -1
    stagnant = 0

    for _ in range(max_rounds):
        await _close_login_popup(page)

        current = await stars.count()
        if current == last:
            stagnant += 1
        else:
            stagnant = 0
            last = current

        if stagnant >= 8:
            break

        await scrollbox.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        await page.wait_for_timeout(pause_ms)

async def _expand_all_reviews(page, max_clicks: int = 80) -> None:
    """
    Click "More/Lainnya" buttons to expand long reviews.
    """
    more = page.get_by_role("button", name=re.compile(r"(more|lainnya)", re.I))
    try:
        n = await more.count()
        for i in range(min(n, max_clicks)):
            try:
                await more.nth(i).click(timeout=800)
            except Exception:
                pass
    except Exception:
        pass


async def _extract_reviews(page, limit: int = 200) -> List[Review]:
    """
    Extract loaded reviews.
    """
    cards = await _get_cards_locator(page)
    if await cards.count() == 0:
        cards = page.locator("div[data-review-id]")
    n = await cards.count()
    n = min(n, limit)

    results: List[Review] = []

    for i in range(n):
        card = cards.nth(i)

        # user name
        user_name = ""
        for sel in ["span.d4r55", "div.d4r55", "[class*='d4r55']"]:
            try:
                el = card.locator(sel).first
                if await el.count() > 0:
                    user_name = _clean_text(await el.inner_text())
                    if user_name:
                        break
            except Exception:
                pass

        # timestamp
        timestamp = ""
        for sel in ["span.rsqaWe", "[class*='rsqaWe']"]:
            try:
                el = card.locator(sel).first
                if await el.count() > 0:
                    timestamp = _clean_text(await el.inner_text())
                    if timestamp:
                        break
            except Exception:
                pass

        # rating
        rating = None
        try:
            star = card.locator("span.kvMYJc[role='img']").first
            if await star.count() > 0:
                aria = await star.get_attribute("aria-label")
                rating = _parse_rating_from_aria(aria or "")
        except Exception:
            pass

        # review text
        text_review = ""
        for sel in ["span.wiI7pd", "div.wiI7pd", "[class*='wiI7pd']"]:
            try:
                el = card.locator(sel).first
                if await el.count() > 0:
                    text_review = _clean_text(await el.inner_text())
                    if text_review:
                        break
            except Exception:
                pass

        results.append(
            Review(
                user_name=user_name,
                rating=rating,
                timestamp=timestamp,
                text_review=text_review,
            )
        )

    return results


# -----------------------------
# Main scraping pipeline
# -----------------------------
async def scrape_google_maps_reviews(
    place_url: str,
    max_reviews: int = 200,
    headless: bool = True,
    max_scrolls: int = 40,
) -> PlaceReviews:
    async with async_playwright() as p:
        # Persistent context keeps login cookies
        context = await p.chromium.launch_persistent_context(
            user_data_dir="gmaps_profile",
            headless=headless,
            slow_mo=0 if headless else 100,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        page = await context.new_page()
        page.set_default_timeout(60000)

        try:
            await page.goto(place_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(1200)

            await _maybe_accept_consent(page)
            await _close_login_popup(page)

            # IMPORTANT: first run, login manually if needed
            # If you see the Login button, login once and rerun.
            # (You can also pause longer here if you want.)
            # await page.wait_for_timeout(60000)

            await page.wait_for_selector("h1.DUwDvf, h1[class*='DUwDvf'], h1", timeout=60000)

            identity = await _get_place_identity(page)

            await _open_reviews_panel(page)
            await _close_login_popup(page)

            # Debug right here (important)
            print("DEBUG cards jftiEf:", await page.locator("div.jftiEf").count())
            print("DEBUG cards data-review-id:", await page.locator("div[data-review-id]").count())
            await page.screenshot(path="debug_in_ulasan.png", full_page=True)

            # total = await _get_total_reviews_count(page)
            # print("DEBUG total reviews shown by page:", total)

            await _scroll_reviews_until_done(page, pause_ms=900, max_rounds=250)
            await _close_login_popup(page)

            await _expand_all_reviews(page)

            reviews = await _extract_reviews(page, limit=5000)

            return PlaceReviews(
                place_url=place_url,
                place_name=identity.get("place_name", ""),
                place_location=identity.get("place_location", ""),
                reviews=reviews,
            )

        except PlaywrightTimeoutError as e:
            try:
                await page.screenshot(path="debug_timeout.png", full_page=True)
            except Exception:
                pass
            raise RuntimeError(f"Timeout while scraping. Saved debug_timeout.png. Details: {e}") from e

        finally:
            await context.close()


def export_results(data: PlaceReviews, out_json: str = "reviews.json", out_csv: str = "reviews.csv") -> None:
    payload: Dict[str, Any] = asdict(data)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    rows = [
        {
            "place_url": data.place_url,
            "place_name": data.place_name,
            "place_location": data.place_location,
            "user_name": r.user_name,
            "rating": r.rating,
            "timestamp": r.timestamp,
            "text_review": r.text_review,
        }
        for r in data.reviews
    ]
    pd.DataFrame(rows).to_csv(out_csv, index=False, encoding="utf-8-sig")

def _parse_total_reviews(text: str) -> Optional[int]:
    # matches (42) or 42 ulasan / reviews
    m = re.search(r"\((\d+)\)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(ulasan|reviews)", text, re.I)
    if m:
        return int(m.group(1))
    return None


async def _get_total_reviews_count(page) -> Optional[int]:
    # Try near rating area
    candidates = [
        "span.F7nice",          # often contains rating + count
        "button[jsaction*='reviews']",
        "div.fontBodyMedium",   # fallback
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                txt = await loc.inner_text()
                n = _parse_total_reviews(txt)
                if n is not None:
                    return n
        except:
            pass
    return None

# -----------------------------
# CLI
# -----------------------------


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Google Maps place URL")
    parser.add_argument("--max_reviews", type=int, default=200)
    parser.add_argument("--max_scrolls", type=int, default=40)
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--headed", action="store_true", help="Run with UI (recommended for debugging)")
    args = parser.parse_args()

    headless_mode = True
    if args.headed:
        headless_mode = False
    elif args.headless:
        headless_mode = True

    result = asyncio.run(
        scrape_google_maps_reviews(
            place_url=args.url,
            max_reviews=args.max_reviews,
            headless=headless_mode,
            max_scrolls=args.max_scrolls,
        )
    )

    print(f"Place: {result.place_name}")
    print(f"Location: {result.place_location}")
    print(f"Reviews scraped: {len(result.reviews)}")

    export_results(result, out_json="reviews.json", out_csv="reviews.csv")
    print("Saved: reviews.json, reviews.csv")