#!/usr/bin/env python3
"""
Evanđelje Audio - Svaki dan scrapa evanđelje s hilp.hr,
generira 10-minutni audio (ElevenLabs), šalje mailom i objavljuje na podcast RSS feed.
"""

import os
import re
import time
import json
import smtplib
import tempfile
import datetime
import requests
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from bs4 import BeautifulSoup
from pydub import AudioSegment


# ── Konfiguracija ──────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "ivan-os@live.com")

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO_AUDIO = "ivanbalic1/evandjelje-audio"
GITHUB_REPO_PAGES = "ivanbalic1/ivanbalic1.github.io"
GITHUB_PAGES_BASE = "https://ivanbalic1.github.io"

TARGET_DURATION_MS = 10 * 60 * 1000  # 10 minuta


# ── Scraping ───────────────────────────────────────────────────────────────────

def get_today_url() -> str:
    days_hr = {
        0: "ponedjeljak", 1: "utorak", 2: "srijeda",
        3: "cetvrtak", 4: "petak", 5: "subota", 6: "nedjelja"
    }
    today = datetime.date.today()
    return f"https://hilp.hr/liturgija-dana/{days_hr[today.weekday()]}-{today.day}-{today.month}-{today.year}/"


def dohvati_stranicu(url: str):
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "hr,en;q=0.9",
        "Referer": "https://hilp.hr/",
    }
    session.get("https://hilp.hr/", headers=headers, timeout=15)
    r = session.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def scrape_evandjelje(url: str) -> dict:
    print(f"Scraping: {url}")
    soup = dohvati_stranicu(url)

    evandjelje_data = {"naslov": "", "referenca": "", "tekst": ""}

    opisi = soup.find_all("div", class_="et_pb_blurb_description")
    print(f"Pronađeno blurb_description divova: {len(opisi)}")

    for opis in opisi:
        tekst = opis.get_text(separator="\n", strip=True)
        if "Čitanje svetog Evanđelja" not in tekst:
            continue

        h4_tagovi = opis.find_all(["h4", "h3", "h2"])
        for i, h in enumerate(h4_tagovi):
            if "Evanđelje" in h.get_text() and "Čitanje" not in h.get_text():
                if i + 1 < len(h4_tagovi):
                    evandjelje_data["referenca"] = h4_tagovi[i + 1].get_text(strip=True)
                if i + 2 < len(h4_tagovi):
                    evandjelje_data["naslov"] = h4_tagovi[i + 2].get_text(strip=True)
                break

        redci = []
        unutar = False
        for p in opis.find_all("p"):
            tekst_p = p.get_text(separator=" ", strip=True)
            if "Čitanje svetog Evanđelja" in tekst_p:
                unutar = True
            if unutar and tekst_p:
                redci.append(tekst_p)
            if unutar and "Riječ Gospodnja" in tekst_p:
                break

        evandjelje_data["tekst"] = " ".join(redci)
        if evandjelje_data["tekst"]:
            break

    if not evandjelje_data["tekst"]:
        raise ValueError("Tekst evanđelja nije pronađen!")

    print(f"Pronađeno: {evandjelje_data['referenca']} — {evandjelje_data['naslov']}")
    print(f"Duljina teksta: {len(evandjelje_data['tekst'])} znakova")
    return evandjelje_data


# ── TTS ────────────────────────────────────────────────────────────────────────

def build_tts_text(evandjelje: dict) -> str:
    return evandjelje["tekst"]


def generate_tts(text: str, output_path: str) -> None:
    print(f"Generiram TTS ({len(text)} znakova)...")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY,
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True
        }
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(resp.content)
    print(f"TTS spremljen: {output_path}")


# ── Audio montaža ──────────────────────────────────────────────────────────────

def build_final_audio(reading_path: str, target_ms: int) -> AudioSegment:
    """
    Raspored: 5s tišina | čitanje | tišina | čitanje | tišina | čitanje | tišina
    ElevenLabs se poziva samo jednom, audio se kopira 3x.
    """
    segment = AudioSegment.from_mp3(reading_path)
    reading_ms = len(segment)
    intro_ms = 5000
    remaining_ms = target_ms - intro_ms - (reading_ms * 3)

    silence_ms = max(1000, remaining_ms // 3) if remaining_ms > 0 else 1000

    print(f"Trajanje jednog čitanja: {reading_ms/1000:.1f}s")
    print(f"Tišina po bloku: {silence_ms/1000:.1f}s")

    final = AudioSegment.silent(duration=intro_ms)
    for i in range(3):
        final += segment
        final += AudioSegment.silent(duration=silence_ms)

    if len(final) < target_ms:
        final += AudioSegment.silent(duration=target_ms - len(final))
    else:
        final = final[:target_ms]

    print(f"Ukupno trajanje: {len(final)/1000:.1f}s ({len(final)/60000:.2f} min)")
    return final


# ── GitHub Release upload ──────────────────────────────────────────────────────

def upload_to_github_release(mp3_path: str, filename: str, evandjelje: dict) -> str:
    """
    Kreira GitHub Release i uploaduje MP3. Vraća URL do fajla.
    """
    today = datetime.date.today()
    tag = f"ep-{today.strftime('%Y-%m-%d')}"
    release_name = f"Evanđelje {today.strftime('%d. %m. %Y.')} — {evandjelje['referenca']}"
    release_body = f"{evandjelje['naslov']}\n\nIzvor: {get_today_url()}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # 1. Provjeri postoji li već release s tim tagom, obriši ga ako da
    print(f"Kreiram GitHub Release: {tag}")
    existing = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO_AUDIO}/releases/tags/{tag}",
        headers=headers,
        timeout=15,
    )
    if existing.status_code == 200:
        old_id = existing.json()["id"]
        print(f"Release već postoji (id={old_id}), brišem...")
        requests.delete(
            f"https://api.github.com/repos/{GITHUB_REPO_AUDIO}/releases/{old_id}",
            headers=headers,
            timeout=15,
        )
        # Obriši i tag
        requests.delete(
            f"https://api.github.com/repos/{GITHUB_REPO_AUDIO}/git/refs/tags/{tag}",
            headers=headers,
            timeout=15,
        )

    r = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO_AUDIO}/releases",
        headers=headers,
        json={
            "tag_name": tag,
            "name": release_name,
            "body": release_body,
            "draft": False,
            "prerelease": False,
        },
        timeout=30,
    )
    r.raise_for_status()
    release = r.json()
    upload_url = release["upload_url"].replace("{?name,label}", "")
    asset_id = release["id"]

    # 2. Upload MP3
    print(f"Uploading MP3 na GitHub Release...")
    file_size = os.path.getsize(mp3_path)
    with open(mp3_path, "rb") as f:
        upload_resp = requests.post(
            f"{upload_url}?name={filename}",
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Content-Type": "audio/mpeg",
                "Content-Length": str(file_size),
            },
            data=f,
            timeout=120,
        )
    upload_resp.raise_for_status()
    mp3_url = upload_resp.json()["browser_download_url"]
    print(f"MP3 dostupan na: {mp3_url}")
    return mp3_url


# ── RSS Feed ───────────────────────────────────────────────────────────────────

def azuriraj_rss(mp3_url: str, mp3_path: str, evandjelje: dict) -> None:
    """
    Dohvaća postojeći feed.xml iz repozitorija, dodaje novi item i commituje ga.
    """
    today = datetime.date.today()
    file_size = os.path.getsize(mp3_path)

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Dohvati postojeći feed.xml (ako postoji)
    existing_items = ""
    existing_sha = None
    r = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO_PAGES}/contents/feed.xml",
        headers=headers,
        timeout=15,
    )
    if r.status_code == 200:
        import base64
        existing_content = base64.b64decode(r.json()["content"]).decode("utf-8")
        existing_sha = r.json()["sha"]
        # Izvuci postojeće <item> elemente
        match = re.search(r"(<item>.*?</item>)", existing_content, re.DOTALL)
        if match:
            # Uzmi sve item tagove
            items = re.findall(r"<item>.*?</item>", existing_content, re.DOTALL)
            # Zadrži zadnjih 30 epizoda
            existing_items = "\n    ".join(items[:30])

    # Novi item
    pub_date = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
    novi_item = f"""<item>
      <title>Evanđelje {today.strftime("%-d. %-m. %Y.")} — {evandjelje["referenca"]}</title>
      <description>{evandjelje["naslov"]} {evandjelje["tekst"][:200]}...</description>
      <enclosure url="{mp3_url}" length="{file_size}" type="audio/mpeg"/>
      <guid>{mp3_url}</guid>
      <pubDate>{pub_date}</pubDate>
    </item>"""

    # Složi cijeli feed
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Evanđelje dana</title>
    <link>https://hilp.hr/liturgija-dana/</link>
    <description>Dnevno evanđelje — čitanje ponovljeno 3 puta unutar 10 minuta</description>
    <language>hr</language>
    <itunes:author>Automatski podcast</itunes:author>
    <itunes:category text="Religion &amp; Spirituality"/>
    <itunes:explicit>false</itunes:explicit>
    {novi_item}
    {existing_items}
  </channel>
</rss>"""

    # Commituj feed.xml u repozitorij
    import base64
    encoded = base64.b64encode(feed.encode("utf-8")).decode("utf-8")
    payload = {
        "message": f"Dodaj evanđelje {today.strftime('%Y-%m-%d')}",
        "content": encoded,
    }
    if existing_sha:
        payload["sha"] = existing_sha

    r = requests.put(
        f"https://api.github.com/repos/{GITHUB_REPO_PAGES}/contents/feed.xml",
        headers=headers,
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    print(f"RSS feed ažuriran: {GITHUB_PAGES_BASE}/feed.xml")


# ── Email ──────────────────────────────────────────────────────────────────────

def send_email(mp3_path: str, evandjelje: dict, recipient: str, mp3_url: str) -> None:
    today = datetime.date.today()
    subject = f"Evanđelje dana — {today.strftime('%d. %m. %Y.')} — {evandjelje['referenca']}"

    body = (
        f"Dobro jutro,\n\n"
        f"U prilogu je audio evanđelje za danas.\n\n"
        f"📖 {evandjelje['referenca']}\n"
        f"✝ {evandjelje['naslov']}\n\n"
        f"Čitanje je ponovljeno 3 puta unutar 10 minuta.\n\n"
        f"🎙️ Podcast RSS feed:\n{GITHUB_PAGES_BASE}/feed.xml\n\n"
        f"Lp,\nVaš automatski podsjetnik"
    )

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with open(mp3_path, "rb") as f:
        part = MIMEBase("audio", "mpeg")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    filename = f"evandjelje-{today.strftime('%d-%m-%Y')}.mp3"
    part.add_header("Content-Disposition", f"attachment; filename={filename}")
    msg.attach(part)

    print(f"Šaljem mail na {recipient}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, recipient, msg.as_string())
    print("Mail poslan!")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    today = datetime.date.today()
    filename = f"evandjelje-{today.strftime('%d-%m-%Y')}.mp3"

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Scrape
        url = get_today_url()
        evandjelje = scrape_evandjelje(url)

        # 2. Generiraj TTS samo jednom
        text = build_tts_text(evandjelje)
        reading_path = os.path.join(tmpdir, "reading.mp3")
        generate_tts(text, reading_path)

        # 3. Spoji u 10-minutni audio
        final_audio = build_final_audio(reading_path, TARGET_DURATION_MS)
        final_path = os.path.join(tmpdir, filename)
        final_audio.export(final_path, format="mp3", bitrate="128k")

        # 4. Upload na GitHub Release
        mp3_url = upload_to_github_release(final_path, filename, evandjelje)

        # 5. Ažuriraj RSS feed
        azuriraj_rss(mp3_url, final_path, evandjelje)

        # 6. Pošalji mail
        send_email(final_path, evandjelje, RECIPIENT_EMAIL, mp3_url)

    print("Gotovo! ✓")


if __name__ == "__main__":
    main()
