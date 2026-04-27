#!/usr/bin/env python3
"""
Red Sienna Finder — Daily scraper
Uses RSS feeds and embedded JSON to reliably pull listings.
"""

import requests
from bs4 import BeautifulSoup
import json
import math
import os
import re
from datetime import datetime, timezone
import time
import hashlib
import xml.etree.ElementTree as ET

LAKEWOOD_LAT = 33.8536
LAKEWOOD_LON = -118.1339
MIN_PRICE = 26000
MAX_PRICE = 46000

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
}

PLATFORM_URLS = {
    'AutoTrader':   'https://www.autotrader.com/cars-for-sale/used-cars/toyota/sienna/lakewood-ca-90712?minPrice=26000&maxPrice=46000&startYear=2021&endYear=2025&trimCodeList=SIENNA%7CXLE&searchRadius=500&extColorsSimple=RED',
    'Cars.com':     'https://www.cars.com/shopping/results/?makes[]=toyota&models[]=toyota-sienna&list_price_max=46000&list_price_min=26000&year_max=2025&year_min=2021&zip=90712&maximum_distance=500&stock_type=used',
    'CarGurus':     'https://www.cargurus.com/Cars/new/nl_Toyota_Sienna_d2280?zip=90712&distance=500&minPrice=26000&maxPrice=46000&minYear=2021&maxYear=2025',
    'TrueCar':      'https://www.truecar.com/used-cars-for-sale/listings/toyota/sienna/?zip=90712&searchRadius=500&price%5Bmax%5D=46000&price%5Bmin%5D=26000&year%5Bmax%5D=2025&year%5Bmin%5D=2021&trim%5B%5D=XLE',
    'Edmunds':      'https://www.edmunds.com/toyota/sienna/used/#zip=90712&radius=500',
    'KBB':          'https://www.kbb.com/toyota/sienna/used-cars/#zip=90712&distance=500&minyear=2021&maxyear=2025&minprice=26000&maxprice=46000',
    'CarsDirect':   'https://www.carsdirect.com/cars-for-sale/toyota/sienna?zip=90712&distance=500&min_price=26000&max_price=46000&min_year=2021&max_year=2025',
    'Craigslist LA':'https://losangeles.craigslist.org/search/cta?query=toyota+sienna+xle&min_price=26000&max_price=46000&sort=date',
    'eBay Motors':  'https://www.ebay.com/sch/Cars-Trucks/6001/i.html?_nkw=toyota+sienna+xle&LH_BIN=1&_udlo=26000&_udhi=46000&LH_ItemCondition=3000',
    'DealerRater':  'https://www.dealerrater.com/cars-for-sale/toyota/sienna/?zip=90712&distance=500&minyear=2021&maxyear=2025&minprice=26000&maxprice=46000',
}


def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return round(2 * R * math.asin(math.sqrt(a)), 1)


def listing_id(url):
    return hashlib.md5(url.strip().encode()).hexdigest()[:12]


def extract_price(text):
    digits = re.sub(r'[^\d]', '', text or '')
    return int(digits) if digits else 0


def load_previous():
    if os.path.exists('listings.json'):
        with open('listings.json') as f:
            return {item['id']: item for item in json.load(f)}
    return {}


def make_listing(title, price_raw, mileage_raw, url, image, platform):
    price = extract_price(price_raw)
    mileage = extract_price(mileage_raw)
    return {
        'id': listing_id(url),
        'title': title,
        'price': price,
        'price_display': price_raw.strip() if price_raw else 'Call for Price',
        'mileage': mileage,
        'mileage_display': mileage_raw.strip() if mileage_raw else 'N/A',
        'distance': None,
        'distance_display': 'N/A',
        'url': url,
        'image': image or '',
        'platform': platform,
        'date_found': datetime.now(timezone.utc).isoformat(),
        'is_new': True,
    }


# ── Craigslist via RSS (most reliable — returns real XML) ─────────────────────

def scrape_craigslist():
    listings = []
    # RSS feed avoids anti-bot JS challenges
    rss_url = 'https://losangeles.craigslist.org/search/cta?format=rss&query=toyota+sienna+xle&min_price=26000&max_price=46000&sort=date'
    try:
        resp = requests.get(rss_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()

        # BeautifulSoup handles RSS 1.0 and 2.0 via xml parser
        soup = BeautifulSoup(resp.text, 'lxml-xml')
        items = soup.find_all('item')
        print(f'  Craigslist RSS: {len(items)} raw items')

        for item in items:
            try:
                title = (item.find('title') or item.find('dc:title') or {}).get_text(strip=True)
                link = (item.find('link') or item.find('guid') or {}).get_text(strip=True)
                desc = (item.find('description') or {}).get_text(strip=True)

                if not title or not link:
                    continue
                if not any(k in title.lower() for k in ['sienna', 'toyota']):
                    continue

                # Price is usually in title like "$32,500" or in description
                price_match = re.search(r'\$[\d,]+', title + ' ' + desc)
                price_raw = price_match.group(0) if price_match else ''
                price = extract_price(price_raw)
                if price and (price < MIN_PRICE or price > MAX_PRICE):
                    continue

                # Image from enclosure or description img tag
                img = ''
                enc = item.find('enclosure')
                if enc and enc.get('url'):
                    img = enc['url']
                else:
                    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc)
                    if img_match:
                        img = img_match.group(1)

                listings.append(make_listing(title, price_raw, '', link, img, 'Craigslist LA'))
            except Exception:
                continue

    except Exception as e:
        print(f'  Craigslist RSS failed: {e}')
        # Fallback: try plain HTML
        try:
            resp2 = requests.get(PLATFORM_URLS['Craigslist LA'], headers=HEADERS, timeout=20)
            soup2 = BeautifulSoup(resp2.text, 'lxml')
            for item in soup2.select('li.cl-search-result, li.result-row')[:40]:
                link_el = item.select_one('a.result-title, a.cl-app-anchor, a[href]')
                if not link_el:
                    continue
                title = link_el.get_text(strip=True)
                if not any(k in title.lower() for k in ['sienna', 'toyota']):
                    continue
                href = link_el.get('href', '')
                if href and not href.startswith('http'):
                    href = 'https://losangeles.craigslist.org' + href
                price_el = item.select_one('.result-price, .priceinfo')
                price_raw = price_el.get_text(strip=True) if price_el else ''
                img_el = item.select_one('img')
                img = img_el.get('src', '') if img_el else ''
                listings.append(make_listing(title, price_raw, '', href, img, 'Craigslist LA'))
        except Exception as e2:
            print(f'  Craigslist HTML fallback failed: {e2}')

    return listings


# ── Cars.com via embedded __NEXT_DATA__ JSON ──────────────────────────────────

def scrape_cars_com():
    listings = []
    url = ('https://www.cars.com/shopping/results/?'
           'makes[]=toyota&models[]=toyota-sienna'
           '&list_price_max=46000&list_price_min=26000'
           '&year_max=2025&year_min=2021'
           '&zip=90712&maximum_distance=500&stock_type=used')
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        # Method 1: Next.js JSON blob
        next_data = soup.find('script', id='__NEXT_DATA__')
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                # Dig through the nested structure looking for listings
                raw = json.dumps(data)
                # Find all listing URLs
                urls_found = re.findall(r'"url"\s*:\s*"(https://www\.cars\.com/vehicledetail/[^"]+)"', raw)
                prices_found = re.findall(r'"primaryPrice"\s*:\s*"([^"]+)"', raw)
                titles_found = re.findall(r'"title"\s*:\s*"([^"]+Toyota Sienna[^"]*)"', raw, re.IGNORECASE)
                mileages_found = re.findall(r'"mileage"\s*:\s*"([^"]+)"', raw)
                images_found = re.findall(r'"firstPhoto"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"', raw)

                for i, listing_url in enumerate(urls_found[:20]):
                    title = titles_found[i] if i < len(titles_found) else 'Toyota Sienna XLE'
                    price_raw = prices_found[i] if i < len(prices_found) else ''
                    mileage_raw = mileages_found[i] if i < len(mileages_found) else ''
                    img = images_found[i] if i < len(images_found) else ''
                    listings.append(make_listing(title, price_raw, mileage_raw, listing_url, img, 'Cars.com'))

                if listings:
                    print(f'  Cars.com (JSON): {len(listings)} listings')
                    return listings
            except Exception as e:
                print(f'  Cars.com JSON parse failed: {e}')

        # Method 2: HTML card scraping
        cards = (soup.select('div[data-qa="vehicle-card"]') or
                 soup.select('div.vehicle-card') or
                 soup.select('[class*="vehicle-card"]'))
        print(f'  Cars.com HTML cards found: {len(cards)}')

        for card in cards[:30]:
            try:
                link = card.select_one('a[href*="vehicledetail"]') or card.select_one('a[href]')
                if not link:
                    continue
                href = link.get('href', '')
                if not href.startswith('http'):
                    href = 'https://www.cars.com' + href

                title_el = (card.select_one('[class*="title"]') or
                            card.select_one('h2') or card.select_one('h3'))
                price_el = (card.select_one('[class*="primary-price"]') or
                            card.select_one('[class*="price"]'))
                mileage_el = (card.select_one('[class*="mileage"]') or
                              card.select_one('[class*="miles"]'))
                img_el = card.select_one('img')

                title = (title_el or link).get_text(strip=True)
                price_raw = price_el.get_text(strip=True) if price_el else ''
                mileage_raw = mileage_el.get_text(strip=True) if mileage_el else ''
                img = ''
                if img_el:
                    img = img_el.get('src') or img_el.get('data-src') or ''
                    if img.startswith('//'):
                        img = 'https:' + img

                listings.append(make_listing(title, price_raw, mileage_raw, href, img, 'Cars.com'))
            except Exception:
                continue

    except Exception as e:
        print(f'  Cars.com failed: {e}')

    return listings


# ── eBay Motors (accessible HTML, no heavy JS protection) ─────────────────────

def scrape_ebay_motors():
    listings = []
    url = ('https://www.ebay.com/sch/Cars-Trucks/6001/i.html'
           '?_nkw=toyota+sienna+xle'
           '&_udlo=26000&_udhi=46000'
           '&LH_ItemCondition=3000'
           '&LH_BIN=1')
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        items = soup.select('.s-item')
        print(f'  eBay Motors raw items: {len(items)}')

        for item in items[:30]:
            try:
                link_el = item.select_one('a.s-item__link')
                if not link_el:
                    continue
                href = link_el.get('href', '')
                if 'ebay.com' not in href:
                    continue

                title_el = item.select_one('.s-item__title')
                price_el = item.select_one('.s-item__price')
                mileage_el = item.select_one('.s-item__subtitle') or item.select_one('.SECONDARY_INFO')
                img_el = item.select_one('img')

                title = (title_el or link_el).get_text(strip=True)
                if 'shop on ebay' in title.lower():
                    continue
                if not any(k in title.lower() for k in ['sienna', 'toyota']):
                    continue

                price_raw = price_el.get_text(strip=True) if price_el else ''
                mileage_raw = mileage_el.get_text(strip=True) if mileage_el else ''
                img = ''
                if img_el:
                    img = img_el.get('src') or img_el.get('data-src') or ''

                listings.append(make_listing(title, price_raw, mileage_raw, href, img, 'eBay Motors'))
            except Exception:
                continue

    except Exception as e:
        print(f'  eBay Motors failed: {e}')

    return listings


# ── CarGurus via embedded JSON ─────────────────────────────────────────────────

def scrape_cargurus():
    listings = []
    url = ('https://www.cargurus.com/Cars/new/nl_Toyota_Sienna_d2280'
           '?zip=90712&distance=500&minPrice=26000&maxPrice=46000'
           '&minYear=2021&maxYear=2025&sortField=PRICE_CHANGE_TIME&sortDir=DESC')
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        for script in soup.find_all('script'):
            text = script.string or ''
            if 'priceInCents' not in text:
                continue
            try:
                match = re.search(r'"listings"\s*:\s*(\[.+?\])\s*,\s*"[a-z]', text, re.DOTALL)
                if not match:
                    continue
                data = json.loads(match.group(1))
                for item in data[:20]:
                    price_cents = item.get('priceInCents') or 0
                    price = price_cents // 100
                    if price and (price < MIN_PRICE or price > MAX_PRICE):
                        continue
                    path = item.get('listingUrl', '') or item.get('vdpUrl', '')
                    full_url = path if path.startswith('http') else 'https://www.cargurus.com' + path
                    mileage = item.get('mileage') or 0
                    img = item.get('mainPictureUrl') or item.get('pictureUrl') or ''
                    listings.append(make_listing(
                        item.get('header') or item.get('listingTitle') or 'Toyota Sienna XLE',
                        f"${price:,}" if price else '',
                        f"{mileage:,} mi" if mileage else '',
                        full_url, img, 'CarGurus'
                    ))
                if listings:
                    break
            except Exception:
                continue

    except Exception as e:
        print(f'  CarGurus failed: {e}')

    return listings


# ── Deduplicate & merge ────────────────────────────────────────────────────────

def deduplicate(listings):
    seen = {}
    for item in listings:
        if item['id'] not in seen:
            seen[item['id']] = item
    return list(seen.values())


def merge_with_previous(new_listings, previous):
    merged = []
    for item in new_listings:
        item['is_new'] = item['id'] not in previous
        if item['id'] in previous:
            item['date_found'] = previous[item['id']]['date_found']
        merged.append(item)
    return sorted(merged, key=lambda x: x['date_found'], reverse=True)


# ── HTML generation ────────────────────────────────────────────────────────────

def generate_html(listings, scraped_platforms, failed_platforms):
    now_str = datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p UTC')
    new_count = sum(1 for l in listings if l.get('is_new'))
    total = len(listings)

    cards_html = ''
    for listing in listings:
        new_badge = '<span class="badge-new">NEW</span>' if listing.get('is_new') else ''
        if listing.get('image'):
            img_html = (f'<img src="{listing["image"]}" alt="{listing["title"]}" loading="lazy" '
                        f'onerror="this.onerror=null;this.src=\'https://placehold.co/400x240/1a0000/cc0000?text=No+Photo\';">')
        else:
            img_html = '<div class="no-photo">No Photo</div>'

        cards_html += f'''
        <div class="card"
             data-price="{listing.get('price', 0) or 0}"
             data-mileage="{listing.get('mileage', 0) or 0}"
             data-distance="{listing.get('distance') or 9999}"
             data-date="{listing['date_found']}">
          <div class="card-img">
            {img_html}
            {new_badge}
            <span class="plat-badge">{listing["platform"]}</span>
          </div>
          <div class="card-body">
            <h3 class="card-title">{listing["title"]}</h3>
            <div class="price">{listing["price_display"]}</div>
            <div class="meta">
              <span>&#128739; {listing["mileage_display"]}</span>
              <span>&#128205; {listing["distance_display"]}</span>
            </div>
            <div class="date-found">Found: {listing["date_found"][:10]}</div>
            <a href="{listing["url"]}" target="_blank" rel="noopener noreferrer" class="btn-view">View Listing &#8594;</a>
          </div>
        </div>'''

    if not cards_html:
        cards_html = '<div class="no-results"><h2>No listings found yet</h2><p>Use the manual search links below while the scraper is tuning.</p></div>'

    manual_links = ''
    for name, url in PLATFORM_URLS.items():
        icon = '&#9989;' if name in scraped_platforms else '&#128279;'
        manual_links += f'<a href="{url}" target="_blank" rel="noopener noreferrer" class="manual-link">{icon} {name}</a>'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Red Toyota Sienna XLE Finder | Lakewood CA</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d0d18; color: #ddd; min-height: 100vh; }}
    header {{ background: linear-gradient(135deg, #1a0000 0%, #2d0000 60%, #180505 100%); border-bottom: 3px solid #cc0000; padding: 2rem 1.5rem; text-align: center; }}
    header h1 {{ font-size: clamp(1.4rem, 4vw, 2.2rem); color: #ff4444; text-shadow: 0 0 24px rgba(255,68,68,.45); }}
    header p {{ color: #aaa; margin-top: .5rem; font-size: .95rem; }}
    .stats {{ display: flex; gap: .75rem; justify-content: center; flex-wrap: wrap; padding: 1rem 1.5rem; background: #11111e; border-bottom: 1px solid #222235; }}
    .stat {{ background: #191928; border: 1px solid #2a2a45; border-radius: 10px; padding: .75rem 1.5rem; text-align: center; min-width: 110px; }}
    .stat .num {{ font-size: 1.9rem; font-weight: 700; color: #ff4444; line-height: 1; }}
    .stat .lbl {{ font-size: .7rem; color: #777; text-transform: uppercase; letter-spacing: .5px; margin-top: 2px; }}
    .updated {{ text-align: center; padding: .6rem; background: #0b0b16; font-size: .75rem; color: #555; border-bottom: 1px solid #191928; }}
    .controls {{ display: flex; gap: .5rem; justify-content: center; align-items: center; flex-wrap: wrap; padding: 1.25rem 1.5rem; background: #11111e; border-bottom: 1px solid #1e1e32; }}
    .controls span {{ color: #666; font-size: .82rem; }}
    .sort-btn {{ background: #191928; border: 1px solid #2a2a45; color: #bbb; padding: .45rem 1rem; border-radius: 6px; cursor: pointer; font-size: .82rem; transition: background .15s, border-color .15s, color .15s; }}
    .sort-btn:hover {{ background: #8b0000; border-color: #cc0000; color: #fff; }}
    .sort-btn.active {{ background: #cc0000; border-color: #ff4444; color: #fff; font-weight: 600; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 1.25rem; padding: 1.5rem; max-width: 1400px; margin: 0 auto; }}
    .card {{ background: #191928; border: 1px solid #2a2a45; border-radius: 12px; overflow: hidden; transition: transform .2s, border-color .2s, box-shadow .2s; display: flex; flex-direction: column; }}
    .card:hover {{ transform: translateY(-4px); border-color: #cc0000; box-shadow: 0 8px 24px rgba(204,0,0,.2); }}
    .card-img {{ position: relative; height: 200px; background: #0d0d18; overflow: hidden; flex-shrink: 0; }}
    .card-img img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .no-photo {{ display: flex; align-items: center; justify-content: center; height: 100%; color: #444; font-size: .85rem; }}
    .badge-new {{ position: absolute; top: 10px; left: 10px; background: #cc0000; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: .68rem; font-weight: 700; text-transform: uppercase; }}
    .plat-badge {{ position: absolute; bottom: 10px; right: 10px; background: rgba(0,0,0,.72); color: #ccc; padding: 2px 8px; border-radius: 4px; font-size: .68rem; }}
    .card-body {{ padding: 1rem; display: flex; flex-direction: column; flex: 1; }}
    .card-title {{ font-size: .95rem; font-weight: 600; color: #e0e0e0; margin-bottom: .4rem; line-height: 1.3; }}
    .price {{ font-size: 1.5rem; font-weight: 700; color: #ff4444; margin-bottom: .4rem; }}
    .meta {{ display: flex; gap: .75rem; font-size: .78rem; color: #777; margin-bottom: .4rem; flex-wrap: wrap; }}
    .date-found {{ font-size: .72rem; color: #484860; margin-bottom: .75rem; flex: 1; }}
    .btn-view {{ display: block; width: 100%; text-align: center; margin-top: auto; background: #cc0000; color: #fff; text-decoration: none; padding: .6rem 1rem; border-radius: 7px; font-weight: 600; font-size: .88rem; transition: background .15s; }}
    .btn-view:hover {{ background: #ee1111; }}
    .no-results {{ grid-column: 1 / -1; text-align: center; padding: 4rem 2rem; color: #555; }}
    .no-results h2 {{ color: #cc0000; margin-bottom: .75rem; }}
    .manual-section {{ max-width: 1400px; margin: 1.5rem auto 2rem; padding: 0 1.5rem; }}
    .manual-section h2 {{ color: #666; font-size: .78rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: .75rem; border-top: 1px solid #1e1e32; padding-top: 1.25rem; }}
    .manual-links {{ display: flex; gap: .6rem; flex-wrap: wrap; }}
    .manual-link {{ background: #191928; border: 1px solid #2a2a45; color: #999; padding: .4rem .85rem; border-radius: 6px; text-decoration: none; font-size: .8rem; transition: border-color .15s, color .15s; }}
    .manual-link:hover {{ border-color: #cc0000; color: #ff6666; }}
    footer {{ text-align: center; padding: 1.5rem; color: #3a3a55; font-size: .76rem; border-top: 1px solid #1a1a2e; }}
    @media (max-width: 500px) {{ .stat .num {{ font-size: 1.5rem; }} .grid {{ padding: 1rem; gap: 1rem; }} }}
  </style>
</head>
<body>
<header>
  <h1>&#128663; Red Toyota Sienna XLE Finder</h1>
  <p>2021&ndash;2025 &nbsp;&bull;&nbsp; $26,000&ndash;$46,000 &nbsp;&bull;&nbsp; Within 500 miles of Lakewood, CA</p>
</header>
<div class="stats">
  <div class="stat"><div class="num">{total}</div><div class="lbl">Total Listings</div></div>
  <div class="stat"><div class="num">{new_count}</div><div class="lbl">New Today</div></div>
  <div class="stat"><div class="num">{len(scraped_platforms)}</div><div class="lbl">Platforms Live</div></div>
</div>
<div class="updated">Last updated: {now_str} &nbsp;&bull;&nbsp; Auto-updates daily through May 17, 2026</div>
<div class="controls">
  <span>Sort:</span>
  <button class="sort-btn active" onclick="sortCards('date',this)">Newest First</button>
  <button class="sort-btn" onclick="sortCards('price_asc',this)">Price &#8593;</button>
  <button class="sort-btn" onclick="sortCards('price_desc',this)">Price &#8595;</button>
  <button class="sort-btn" onclick="sortCards('mileage',this)">Mileage &#8593;</button>
  <button class="sort-btn" onclick="sortCards('distance',this)">Distance &#8593;</button>
</div>
<div class="grid" id="grid">
  {cards_html}
</div>
<div class="manual-section">
  <h2>&#128279; Search Manually on All Platforms</h2>
  <div class="manual-links">{manual_links}</div>
</div>
<footer>Red Toyota Sienna XLE Finder &nbsp;&bull;&nbsp; Lakewood CA 90712 &nbsp;&bull;&nbsp; Runs daily until May 17, 2026</footer>
<script>
(function(){{
  var grid = document.getElementById('grid');
  window.sortCards = function(method, btn) {{
    var cards = Array.from(grid.querySelectorAll('.card'));
    cards.sort(function(a,b){{
      switch(method){{
        case 'price_asc':  return (parseInt(a.dataset.price)||999999)-(parseInt(b.dataset.price)||999999);
        case 'price_desc': return (parseInt(b.dataset.price)||0)-(parseInt(a.dataset.price)||0);
        case 'mileage':    return (parseInt(a.dataset.mileage)||999999)-(parseInt(b.dataset.mileage)||999999);
        case 'distance':   return (parseFloat(a.dataset.distance)||9999)-(parseFloat(b.dataset.distance)||9999);
        default:           return new Date(b.dataset.date)-new Date(a.dataset.date);
      }}
    }});
    cards.forEach(function(c){{grid.appendChild(c);}});
    document.querySelectorAll('.sort-btn').forEach(function(el){{el.classList.remove('active');}});
    if(btn) btn.classList.add('active');
  }};
}})();
</script>
</body>
</html>'''


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Red Sienna Finder starting — {datetime.now(timezone.utc).isoformat()}")
    previous = load_previous()
    all_listings = []
    scraped_platforms = []
    failed_platforms = []

    scrapers = [
        ('Craigslist LA', scrape_craigslist),
        ('eBay Motors',   scrape_ebay_motors),
        ('Cars.com',      scrape_cars_com),
        ('CarGurus',      scrape_cargurus),
    ]

    for name, fn in scrapers:
        print(f'Scraping {name}...')
        try:
            results = fn()
            if results:
                all_listings.extend(results)
                scraped_platforms.append(name)
                print(f'  -> {len(results)} listings kept')
            else:
                failed_platforms.append(name)
                print(f'  -> 0 listings (blocked or no match)')
        except Exception as e:
            print(f'  -> Error: {e}')
            failed_platforms.append(name)
        time.sleep(2)

    all_listings = deduplicate(all_listings)
    all_listings = merge_with_previous(all_listings, previous)

    with open('listings.json', 'w') as f:
        json.dump(all_listings, f, indent=2)
    print(f'Saved {len(all_listings)} total listings')

    html = generate_html(all_listings, scraped_platforms, failed_platforms)
    with open('index.html', 'w') as f:
        f.write(html)
    print('Generated index.html')

    new_count = sum(1 for l in all_listings if l.get('is_new'))
    print(f'NEW_COUNT:{new_count}')
    print(f'TOTAL_COUNT:{len(all_listings)}')


if __name__ == '__main__':
    main()
