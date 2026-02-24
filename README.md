# 🗺️ Google Maps Scraper Project

A Playwright-based Python scraper for:

- 🔎 Extracting Google Maps short links (`maps.app.goo.gl`)
- 📝 Scraping reviews from a single place
- 🔁 Batch scraping multiple places safely (chunked mode)
- 💾 Appending results into master JSON & CSV files

> Built for research and data collection purposes.

---

# 📂 Project Structure

```
Google-Maps-Scraper-Project/
│
├── gmaps_get_place_links.py      # Get short links from search query
├── google_maps_scraping.py       # Scrape reviews from one place
├── batch_scrape.py               # Batch scrape multiple links (append mode)
│
├── place_links.json              # Generated short links
├── all_places_reviews.json       # Master JSON output (appended)
├── all_places_reviews.csv        # Master CSV output (appended)
│
├── progress_state.json           # Resume progress tracking
├── gmaps_profile_partX/          # Persistent browser sessions
│
└── README.md
```

---

# 🚀 Features

## 1️⃣ Extract Short Links from Search Query

Input:

```
SPKLU Surabaya
```

Output file:

```
place_links_spklu_surabaya.json
```

Example content:

```json
[
  "https://maps.app.goo.gl/XXXX",
  "https://maps.app.goo.gl/YYYY"
]
```

---

## 2️⃣ Scrape Reviews from a Single Place

Extracted data:

- Place name  
- Address  
- User name  
- Rating  
- Timestamp  
- Full review text  

Outputs:

```
reviews.json
reviews.csv
```

---

## 3️⃣ Batch Scraping (Append Mode)

- Scrapes in chunks (default: 5 links per run)
- Appends results into:
  - `all_places_reviews.json`
  - `all_places_reviews.csv`
- Uses resume system (`progress_state.json`)
- Uses fresh browser profile per batch
- Adds delay to reduce throttling

---

# ⚙️ Installation

## 1️⃣ Install Dependencies

```bash
pip install playwright pandas
playwright install chromium
```

---

# 🔐 Login Requirement (IMPORTANT)

Google Maps often shows:

- Limited View
- Infinite loading
- Reviews stuck loading

This project uses **persistent browser profiles**.

Each batch run creates:

```
gmaps_profile_part1/
gmaps_profile_part2/
gmaps_profile_part3/
...
```

### First Run (Login Required)

```bash
python google_maps_scraping.py --url "PLACE_URL" --headed
```

Login manually in the opened browser window.

After login, the session will be reused during that batch run.

---

# 🔎 Usage Guide

---

## 🔹 Step 1 — Get Short Links

```bash
python gmaps_get_place_links.py --q "SPKLU Surabaya"
```

Output:

```
place_links.json
```

---

## 🔹 Step 2 — Scrape Single Place

```bash
python google_maps_scraping.py --url "PLACE_URL" --headed
```

---

## 🔹 Step 3 — Batch Scrape (Append to Master Files)

```bash
python batch_scrape.py --headed
```

This will:

- Scrape next 5 links
- Append results into:
  - `all_places_reviews.json`
  - `all_places_reviews.csv`
- Update `progress_state.json`

Run the same command again to continue scraping the next 5 links.

---

# 📊 Output Format

## Master JSON

```json
[
  {
    "place_url": "...",
    "place_name": "...",
    "place_location": "...",
    "reviews": [
      {
        "user_name": "...",
        "rating": 5,
        "timestamp": "2 weeks ago",
        "text_review": "..."
      }
    ]
  }
]
```

---

## Master CSV

| place_url | place_name | place_location | user_name | rating | timestamp | text_review |
|-----------|------------|----------------|-----------|--------|-----------|-------------|

---

# 🧠 Technical Notes

- Uses Playwright (Chromium)
- Handles:
  - Consent popups
  - Login overlays
  - Infinite scroll
  - Dynamic review loading
- Uses scroll-until-stagnant strategy
- Uses throttling delay to reduce blocking
- Uses resume system for batch scraping

---

# ⚠️ Limitations

- Google Maps DOM structure may change.
- Excessive scraping may trigger rate limiting.
- Login session can degrade after heavy scraping.
- Recommended chunk size: 5 links per run.

---

# 🛠 Recommended Workflow

1. Extract links  
2. Scrape in small chunks  
3. Wait between runs  
4. Use master output as final dataset  

---

# 📜 Disclaimer

This project is intended for research and educational purposes only.

Please ensure compliance with:

- Google Terms of Service  
- Local data regulations  
- Ethical scraping practices