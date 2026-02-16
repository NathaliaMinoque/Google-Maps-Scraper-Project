import asyncio
import json
import re
from urllib.parse import quote_plus
from typing import List, Set

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


def build_maps_search_url(query: str) -> str:
    # Google Maps search URL
    return f"https://www.google.com/maps/search/{quote_plus(query)}"


async def maybe_accept_consent(page) -> None:
    # Best-effort consent handling
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
    """
    Scrolls the LEFT results list. Google Maps results are in a scrollable div.
    """
    # Common scroll containers for search results list (Maps changes often)
    candidates = [
        "div[role='feed']",                          # often used for lists
        "div.m6QErb.DxyBCb.kA9KIf.dS8AEf",           # common scroll panel
        "div.m6QErb.DxyBCb.kA9KIf",                  # fallback panel
    ]

    panel = None
    for sel in candidates:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            panel = loc
            break

    if panel is None:
        # If we can't find a scroll panel, just return.
        return

    last_height = None
    stagnant = 0

    for _ in range(max_rounds):
        # Get current scroll height
        try:
            height = await panel.evaluate("el => el.scrollHeight")
        except Exception:
            height = None

        if height is not None and last_height is not None and height == last_height:
            stagnant += 1
        else:
            stagnant = 0
            last_height = height

        # Stop if list no longer grows
        if stagnant >= 6:
            break

        # Scroll down
        try:
            await panel.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        except Exception:
            # fallback: mouse wheel
            try:
                await page.mouse.wheel(0, 2500)
            except Exception:
                pass

        await page.wait_for_timeout(pause_ms)


async def extract_place_links(page) -> List[str]:
    """
    Extracts unique place links from the current DOM.

    We look for anchors that contain "/maps/place/".
    """
    anchors = page.locator("a[href*='/maps/place/']")
    n = await anchors.count()

    links: Set[str] = set()
    for i in range(n):
        href = await anchors.nth(i).get_attribute("href")
        if not href:
            continue

        # Clean & normalize: keep only the base place URL up to '?' (optional)
        # (some hrefs are relative, some absolute)
        if href.startswith("/"):
            href = "https://www.google.com" + href

        # Keep only valid place URLs
        if "/maps/place/" in href:
            # remove very long tracking query parts if you want cleaner links
            # but keep enough to remain valid
            href_clean = href.split("&")[0]
            links.add(href_clean)

    return sorted(links)


async def get_all_place_links(query: str, headless: bool = False) -> List[str]:
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

            # Wait until results start appearing
            # If the query yields a single place directly, Maps might show place page.
            await page.wait_for_timeout(1500)

            # Scroll results list to load more
            all_links: Set[str] = set()

            for _ in range(6):  # multiple passes: scroll + collect
                await scroll_results_panel(page, max_rounds=40, pause_ms=800)
                links = await extract_place_links(page)
                before = len(all_links)
                all_links.update(links)
                after = len(all_links)

                # If no new links were found in a full pass, we’re likely done
                if after == before:
                    break

            return sorted(all_links)

        except PlaywrightTimeoutError as e:
            await page.screenshot(path="debug_search_timeout.png", full_page=True)
            raise RuntimeError(
                f"Timeout. Saved debug_search_timeout.png. Details: {e}"
            ) from e

        finally:
            await context.close()
            await browser.close()


def save_links(links: List[str], out_json: str = "place_links.json") -> None:
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)


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

    save_links(links, out_json="place_links.json")
    print("Saved: place_links.json")