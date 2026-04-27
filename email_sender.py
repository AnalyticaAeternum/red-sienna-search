#!/usr/bin/env python3
"""
Red Sienna Finder — Email sender via Resend API
"""

import json
import os
import requests
from datetime import datetime, timezone

RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
PAGES_URL = 'https://analyticaaeternum.github.io/red-sienna-search'
FROM_EMAIL = 'onboarding@resend.dev'
RECIPIENTS = ['janusventer@proton.me', 'venterlm26@gmail.com']


def load_listings():
    if os.path.exists('listings.json'):
        with open('listings.json') as f:
            return json.load(f)
    return []


def card_html(listing):
    img = ''
    if listing.get('image'):
        img = f'<img src="{listing["image"]}" width="100%" style="height:180px;object-fit:cover;border-radius:6px;display:block;margin-bottom:10px;" alt="">'
    return f'''
    <div style="background:#1a1a2e;border:1px solid #cc0000;border-radius:10px;padding:16px;margin-bottom:14px;">
      {img}
      <div style="font-size:15px;font-weight:600;color:#e0e0e0;margin-bottom:4px;">{listing["title"]}</div>
      <div style="font-size:22px;font-weight:700;color:#ff4444;margin-bottom:6px;">{listing["price_display"]}</div>
      <div style="font-size:12px;color:#888;margin-bottom:12px;">
        &#128739; {listing["mileage_display"]} &nbsp;&bull;&nbsp;
        &#128205; {listing["distance_display"]} &nbsp;&bull;&nbsp;
        {listing["platform"]}
      </div>
      <a href="{listing["url"]}"
         style="display:inline-block;background:#cc0000;color:#fff;text-decoration:none;
                padding:9px 18px;border-radius:6px;font-weight:700;font-size:13px;">
        View Listing &#8594;
      </a>
    </div>'''


def send_email(listings):
    today = datetime.now(timezone.utc).strftime('%B %d, %Y')
    new_listings = [l for l in listings if l.get('is_new')]
    total = len(listings)
    new_count = len(new_listings)

    highlights = new_listings[:3] if new_listings else listings[:3]
    cards = ''.join(card_html(l) for l in highlights)
    section_title = 'Latest New Listings' if new_listings else 'Latest Listings'

    if not cards:
        cards = '<p style="color:#666;font-size:14px;">No listings found today. Use the page links below to search manually.</p>'

    subject = f"&#128663; Red Sienna Finder — {today} — {total} Listings ({new_count} New)"

    html_body = f'''<!DOCTYPE html>
<html>
<body style="margin:0;padding:20px;background:#0d0d18;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:580px;margin:0 auto;">

  <div style="background:linear-gradient(135deg,#1a0000,#2d0000);border-bottom:3px solid #cc0000;
              padding:24px;border-radius:12px 12px 0 0;text-align:center;">
    <h1 style="color:#ff4444;font-size:22px;margin:0;text-shadow:0 0 20px rgba(255,68,68,.4);">
      &#128663; Red Toyota Sienna XLE Finder
    </h1>
    <p style="color:#aaa;margin:8px 0 0;font-size:14px;">{today}</p>
  </div>

  <div style="background:#11111e;padding:16px;display:flex;gap:12px;">
    <div style="background:#191928;border:1px solid #2a2a45;border-radius:8px;
                padding:14px 20px;flex:1;text-align:center;">
      <div style="font-size:28px;font-weight:700;color:#ff4444;line-height:1;">{total}</div>
      <div style="font-size:11px;color:#666;text-transform:uppercase;margin-top:3px;">Total Listings</div>
    </div>
    <div style="background:#191928;border:1px solid #2a2a45;border-radius:8px;
                padding:14px 20px;flex:1;text-align:center;">
      <div style="font-size:28px;font-weight:700;color:#ff4444;line-height:1;">{new_count}</div>
      <div style="font-size:11px;color:#666;text-transform:uppercase;margin-top:3px;">New Today</div>
    </div>
  </div>

  <div style="background:#11111e;padding:12px 16px 16px;">
    <a href="{PAGES_URL}"
       style="display:block;background:#cc0000;color:#fff;text-decoration:none;
              padding:14px;border-radius:8px;font-size:16px;font-weight:700;text-align:center;">
      &#128279; Open Full Results Page
    </a>
  </div>

  <div style="background:#0d0d18;padding:16px;">
    <h2 style="color:#ff4444;font-size:12px;text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;">
      {section_title}
    </h2>
    {cards}
  </div>

  <div style="background:#11111e;padding:14px;border-radius:0 0 12px 12px;text-align:center;">
    <p style="color:#3a3a55;font-size:11px;margin:0;">
      Red Sienna Finder &bull; Lakewood CA &bull; Daily through May 17, 2026
    </p>
  </div>

</div>
</body>
</html>'''

    payload = {
        'from': FROM_EMAIL,
        'to': RECIPIENTS,
        'subject': subject,
        'html': html_body,
    }

    resp = requests.post(
        'https://api.resend.com/emails',
        headers={
            'Authorization': f'Bearer {RESEND_API_KEY}',
            'Content-Type': 'application/json',
        },
        json=payload,
        timeout=15,
    )

    if resp.status_code in (200, 201):
        print(f'Email sent successfully — subject: {subject}')
    else:
        print(f'Email failed ({resp.status_code}): {resp.text}')
        resp.raise_for_status()


def main():
    if not RESEND_API_KEY:
        print('RESEND_API_KEY not set — skipping email')
        return
    listings = load_listings()
    send_email(listings)


if __name__ == '__main__':
    main()
