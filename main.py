#!/usr/bin/env python3
"""
Debug skripta — ispiši HTML strukturu oko sekcije evanđelja.
Pokreni: python debug_scraper.py
"""

import requests
from bs4 import BeautifulSoup
import datetime

days_hr = {
    0: "ponedjeljak", 1: "utorak", 2: "srijeda",
    3: "cetvrtak", 4: "petak", 5: "subota", 6: "nedjelja"
}
today = datetime.date.today()
day_name = days_hr[today.weekday()]
date_str = today.strftime("%-d-%-m-%Y")
url = f"https://hilp.hr/liturgija-dana/{day_name}-{date_str}/"
print(f"URL: {url}\n")

resp = requests.get(url, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Pronađi sve tagove koji sadrže "Evanđelje" ili "evanđelja"
print("=== SVI TAGOVI KOJI SADRŽE 'vanđelj' ===")
for tag in soup.find_all(True):
    if "vanđelj" in tag.get_text().lower() and tag.name in ["h1","h2","h3","h4","h5","p","div","span"]:
        # Samo direktni tekst, ne children
        direct_text = tag.get_text(strip=True)[:100]
        print(f"  <{tag.name}> : {repr(direct_text)}")

print("\n=== RAW HTML OKO EVANĐELJA (±5 tagova) ===")
all_tags = soup.find_all(["h1","h2","h3","h4","h5","p"])
for i, tag in enumerate(all_tags):
    if "vanđelj" in tag.get_text().lower():
        start = max(0, i-2)
        end = min(len(all_tags), i+10)
        for t in all_tags[start:end]:
            print(f"  <{t.name}> {repr(t.get_text(strip=True)[:120])}")
        break
