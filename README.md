# 🗺️ Google Maps Scraper Project

A Playwright-based Python scraper for:

- 🔎 Extracting place links from Google Maps search queries  
- 📝 Scraping reviews from individual place pages  
- 🔁 Batch scraping multiple locations automatically  
- 💾 Exporting structured JSON and CSV outputs  

> Built for research and data collection purposes.

---

## 📂 Project Structure

```
Google-Maps-Scraper-Project/
│
├── google_maps_scraping.py       # Scrape reviews from a single place
├── gmaps_get_place_links.py      # Get all place links from a search query
├── batch_scrape_reviews.py       # Loop through all place links
├── place_links.json              # Generated list of place URLs
├── all_places_reviews.json       # Batch output (nested JSON)
├── all_places_reviews.csv        # Batch output (flat CSV)
├── gmaps_profile/                # Persistent browser session (ignored)
└── README.md
```

---

## 🚀 Features

### 1️⃣ Extract Place Links From Search

Input:

```
"SPKLU Surabaya"
```

Output:

```json
[
  "https://www.google.com/maps/place/...",
  "https://www.google.com/maps/place/...",
  ...
]
```

Saved to:

```
place_links.json
```

---

### 2️⃣ Scrape Reviews From a Single Place

Extracts:

- Place name  
- Address  
- User name  
- Rating  
- Timestamp  
- Full review text  

Exports:

- `reviews.json`  
- `reviews.csv`  

---

### 3️⃣ Batch Scraping Multiple Places

Automatically loops through:

```
place_links.json
```

And generates:

- `all_places_reviews.json`  
- `all_places_reviews.csv`  

---

## ⚙️ Installation

### 1️⃣ Install dependencies

```bash
pip install playwright pandas
playwright install chromium
```

---

## 🔐 Login Requirement (Important)

Google Maps may show a **limited view** when not logged in.

This project uses a **persistent browser profile**:

```
gmaps_profile/
```

### First Run (Login Once)

```bash
python google_maps_scraping.py --url "YOUR_PLACE_URL" --headed
```

Login manually in the browser window.

After that, your session is saved and reused automatically.

---

## 🔎 Usage

---

### 🔹 Step 1 — Get All Place Links

```bash
python gmaps_get_place_links.py --q "SPKLU Surabaya"
```

Output:

```
place_links.json
```

---

### 🔹 Step 2 — Scrape Single Place Reviews

```bash
python google_maps_scraping.py --url "PLACE_URL" --headed
```

Output:

```
reviews.json
reviews.csv
```

---

### 🔹 Step 3 — Batch Scrape All Places

```bash
python batch_scrape_reviews.py
```

Output:

```
all_places_reviews.json
all_places_reviews.csv
```

---

## 📊 Output Format

### JSON Structure

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

### CSV Structure

| place_url | place_name | place_location | user_name | rating | timestamp | text_review |
|-----------|------------|----------------|-----------|--------|-----------|-------------|

---

## 🧠 Technical Details

- Uses **Playwright (Chromium)**
- Handles:
  - Consent popups
  - Login overlay
  - Infinite scroll
  - Dynamic content loading
- Uses persistent browser session to avoid limited view
- Scroll-until-stagnant logic for maximum review extraction

---

## ⚠️ Notes & Limitations

- Google Maps is dynamic and may change DOM structure.
- Not all reviews may load due to throttling or UI limits.
- Excessive scraping may trigger rate limiting.
- Intended for research and educational purposes.

---

## 🛠 Recommended Improvements (Future Work)

- Resume system (continue from last scraped link)
- Proxy rotation support
- Parallel scraping
- Structured logging
- Docker container support
- CLI argument enhancements

---

## 📜 License

This project is for research and educational use.

Please ensure compliance with:

- Google Terms of Service
- Local data regulations