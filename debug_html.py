#!/usr/bin/env python3
"""
Spremi sirovi HTML stranice da vidimo što GitHub Actions zapravo dobiva.
"""
import requests
from bs4 import BeautifulSoup
import datetime

days_hr = {
    0: "ponedjeljak", 1: "utorak", 2: "srijeda",
    3: "cetvrtak", 4: "petak", 5: "subota", 6: "nedjelja"
}
today = datetime.date.today()
url = f"https://hilp.hr/liturgija-dana/{days_hr[today.weekday()]}-{today.day}-{today.month}-{today.year}/"
print(f"URL: {url}")

session = requests.Session()
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "hr,en;q=0.9",
    "Referer": "https://hilp.hr/",
}
session.get("https://hilp.hr/", headers=headers, timeout=15)
r = session.get(url, headers=headers, timeout=15)
print(f"Status: {r.status_code}")

soup = BeautifulSoup(r.text, "html.parser")

# 1. Sve div klase koje postoje na stranici
print("\n=== SVE DIV KLASE (koje sadrže 'pb' ili 'entry' ili 'content') ===")
seen = set()
for div in soup.find_all("div", class_=True):
    for cls in div.get("class", []):
        if any(x in cls for x in ["pb", "entry", "content", "post", "article"]):
            if cls not in seen:
                seen.add(cls)
                print(f"  {cls}")

# 2. Traži "Čitanje svetog Evanđelja" u bilo kojem tagu
print("\n=== TAGOVI KOJI SADRŽE 'Čitanje svetog Evanđelja' ===")
for tag in soup.find_all(True):
    if "Čitanje svetog Evanđelja" in tag.get_text():
        if tag.name in ["p", "div", "span", "h1","h2","h3","h4","h5"]:
            classes = " ".join(tag.get("class", []))
            print(f"  <{tag.name} class='{classes}'> parent=<{tag.parent.name} class='{' '.join(tag.parent.get('class', []))}'>")

# 3. Spremi prvih 5000 znakova HTML-a za inspekciju
print("\n=== PRVIH 3000 ZNAKOVA HTML-a ===")
print(r.text[:3000])
