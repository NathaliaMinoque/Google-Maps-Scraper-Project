import asyncio
import json
import re
import random
from urllib.parse import quote_plus
from typing import List, Set, Optional

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


def build_maps_search_url(query: str) -> str:
    return f"https://www.google.com/maps/search/{quote_plus(query)}"


async def maybe_accept_consent(page) -> None:
    patterns = [
        re.compile(r"accept", re.I),
        re.compile(r"i agree", re.I),
        re.compile(r"setuju", re.I),
        re.compile(r"terima", re.I),
    ]
    try:
        for pat in patterns:
            btn = page.get_by_role("button", name=pat)
            if await btn.count() > 0:
                await btn.first.click(timeout=2000)
                await page.wait_for_timeout(800)
                return
    except Exception:
        pass


async def scroll_results_panel(page, max_rounds: int = 80, pause_ms: int = 800) -> None:
    candidates = [
        "div[role='feed']",
        "div.m6QErb.DxyBCb.kA9KIf.dS8AEf",
        "div.m6QErb.DxyBCb.kA9KIf",
    ]

    panel = None
    for sel in candidates:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            panel = loc
            break

    if panel is None:
        return

    last_height = None
    stagnant = 0

    for _ in range(max_rounds):
        try:
            height = await panel.evaluate("el => el.scrollHeight")
        except Exception:
            height = None

        if height is not None and last_height is not None and height == last_height:
            stagnant += 1
        else:
            stagnant = 0
            last_height = height

        if stagnant >= 6:
            break

        try:
            await panel.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        except Exception:
            try:
                await page.mouse.wheel(0, 2500)
            except Exception:
                pass

        await page.wait_for_timeout(pause_ms)


async def get_maps_app_short_link(context, place_url: str) -> Optional[str]:
    """
    Open a place page, open Share dialog, and extract the 'Link to share'
    which is usually a maps.app.goo.gl short URL.
    """
    page = await context.new_page()
    page.set_default_timeout(60000)

    try:
        await page.goto(place_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
        await maybe_accept_consent(page)

        # Click Share / Bagikan
        share_btn = page.get_by_role("button", name=re.compile(r"share|bagikan", re.I))
        if await share_btn.count() == 0:
            share_btn = page.locator("[aria-label*='Share' i], [aria-label*='Bagikan' i]")

        if await share_btn.count() == 0:
            return None

        await share_btn.first.click(timeout=15000)
        await page.wait_for_timeout(1200)

        # Look for the input containing the short link
        inputs = page.locator("input[type='text']")
        n = await inputs.count()
        for i in range(n):
            try:
                val = await inputs.nth(i).input_value()
                if val and "maps.app.goo.gl" in val:
                    return val.strip()
            except Exception:
                pass

        # Rare fallback: link text node
        text_link = page.locator("text=/https:\\/\\/maps\\.app\\.goo\\.gl\\//")
        if await text_link.count() > 0:
            txt = (await text_link.first.inner_text()).strip()
            if "maps.app.goo.gl" in txt:
                return txt

        return None

    finally:
        await page.close()


async def extract_place_links(page) -> Set[str]:
    anchors = page.locator("a[href*='/maps/place/']")
    n = await anchors.count()

    raw_links: Set[str] = set()
    for i in range(n):
        href = await anchors.nth(i).get_attribute("href")
        if not href:
            continue
        if href.startswith("/"):
            href = "https://www.google.com" + href
        if "/maps/place/" in href:
            raw_links.add(href.split("&")[0])

    return raw_links

async def convert_links_to_short(context, raw_links: List[str]) -> List[str]:
    clean_short_links: List[str] = []

    for idx, link in enumerate(raw_links, start=1):
        print(f"Converting {idx}/{len(raw_links)} (long): {link}")

        short_link = await get_maps_app_short_link(context, link)
        if short_link:
            print(f"  -> short: {short_link}")
            clean_short_links.append(short_link)
        else:
            print("  -> short: FAILED (keeping long)")
            clean_short_links.append(link)

        await asyncio.sleep(random.uniform(1.5, 3.5))

    # unique + stable order
    seen = set()
    out = []
    for x in clean_short_links:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

async def get_all_place_links(query: str, headless: bool = False) -> List[str]:
    """
    Main pipeline:
    - open maps search
    - scroll results
    - extract place links
    - convert each to maps.app.goo.gl share link
    """
    url = build_maps_search_url(query)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=0 if headless else 80,
            args=["--no-sandbox"],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="id-ID",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = await context.new_page()
        page.set_default_timeout(60000)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(1500)
            await maybe_accept_consent(page)

            all_raw_links: Set[str] = set()

            for round_no in range(1, 7):
                print(f"\n--- Scroll Round {round_no} ---")

                await scroll_results_panel(page, max_rounds=40, pause_ms=800)

                raw_links = await extract_place_links(page)

                before = len(all_raw_links)
                all_raw_links.update(raw_links)
                after = len(all_raw_links)

                print(f"New long links this round: {after - before}")
                print(f"Total unique long links so far: {after}")

                if after == before:
                    print("No new links found. Stopping scroll.")
                    break

            # Convert once at the end
            raw_list = sorted(all_raw_links)
            print(f"\nTotal long links collected: {len(raw_list)}")
            print("Now converting to maps.app.goo.gl links...\n")

            short_links = await convert_links_to_short(context, raw_list)
            return short_links

        except PlaywrightTimeoutError as e:
            await page.screenshot(path="debug_search_timeout.png", full_page=True)
            raise RuntimeError(f"Timeout. Saved debug_search_timeout.png. Details: {e}") from e

        finally:
            await context.close()
            await browser.close()


def save_links(links: List[str], out_json: str = "place_links.json") -> None:
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)

def make_safe_filename(text: str) -> str:
    """
    Convert search query into safe filename:
    - replace spaces with _
    - remove special characters
    - lowercase (optional)
    """
    text = text.strip().replace(" ", "_")
    text = re.sub(r"[^a-zA-Z0-9_]+", "", text)
    return text.lower()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--q", required=True, help='Search query, e.g. "SPKLU Surabaya"')
    parser.add_argument("--headless", action="store_true", help="Run headless")
    args = parser.parse_args()

    links = asyncio.run(get_all_place_links(args.q, headless=args.headless))

    print(f"Query: {args.q}")
    print(f"Found links: {len(links)}")
    print(links[:10], "..." if len(links) > 10 else "")

    safe_query = make_safe_filename(args.q)
    output_file = f"place_links_{safe_query}.json"

    save_links(links, out_json=output_file)

    print(f"Saved: {output_file}")