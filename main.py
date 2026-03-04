#!/usr/bin/env python3
"""
Evanđelje Audio - Svaki dan scrapa evanđelje s hilp.hr,
generira 10-minutni audio (ElevenLabs) i šalje mailom.
"""

import os
import re
import time
import smtplib
import tempfile
import datetime
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from bs4 import BeautifulSoup, NavigableString, Tag
from pydub import AudioSegment


# ── Konfiguracija (čita iz environment varijabli) ──────────────────────────────
ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "ivan-os@live.com")

TARGET_DURATION_MS = 10 * 60 * 1000  # 10 minuta


# ── Scraping ───────────────────────────────────────────────────────────────────

def get_today_url() -> str:
    days_hr = {
        0: "ponedjeljak", 1: "utorak", 2: "srijeda",
        3: "cetvrtak", 4: "petak", 5: "subota", 6: "nedjelja"
    }
    today = datetime.date.today()
    day_name = days_hr[today.weekday()]
    return f"https://hilp.hr/liturgija-dana/{day_name}-{today.day}-{today.month}-{today.year}/"


def scrape_evandjelje(url: str) -> dict:
    """
    Izvlači evanđelje koristeći et_pb_blurb divove (isti pristup kao Kindle skripta).
    Tekst ide od 'Čitanje svetog Evanđelja' do 'Riječ Gospodnja.'
    """
    print(f"Scraping: {url}")

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

    soup = BeautifulSoup(r.text, "html.parser")

    # Isti pristup kao Kindle skripta — et_pb_blurb divovi
    blurbovi = soup.find_all(
        "div",
        class_=lambda c: c and "et_pb_blurb" in " ".join(c) and "tb_footer" not in " ".join(c)
    )
    print(f"Pronađeno blurbova: {len(blurbovi)}")

    evandjelje_data = {"naslov": "", "referenca": "", "tekst": ""}

    for blurb in blurbovi:
        tekst_blurba = blurb.get_text(separator="\n", strip=True)

        if "Evanđelje" not in tekst_blurba:
            continue
        if "Čitanje svetog Evanđelja" not in tekst_blurba:
            continue

        # Izvuci referencu i naslov iz h4 tagova unutar blurba
        h4_tagovi = blurb.find_all(["h4", "h3", "h2"])
        for i, h in enumerate(h4_tagovi):
            if "Evanđelje" in h.get_text() and "Čitanje" not in h.get_text():
                if i + 1 < len(h4_tagovi):
                    evandjelje_data["referenca"] = h4_tagovi[i + 1].get_text(strip=True)
                if i + 2 < len(h4_tagovi):
                    evandjelje_data["naslov"] = h4_tagovi[i + 2].get_text(strip=True)
                break

        # Skupi tekst od "Čitanje svetog Evanđelja" do "Riječ Gospodnja."
        redci = []
        unutar = False
        for p in blurb.find_all("p"):
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
        raise ValueError("Tekst evanđelja nije pronađen! Provjeri strukturu stranice.")

    print(f"Pronađeno evanđelje: {evandjelje_data['referenca']} — {evandjelje_data['naslov']}")
    print(f"Duljina teksta: {len(evandjelje_data['tekst'])} znakova")
    return evandjelje_data


# ── TTS ────────────────────────────────────────────────────────────────────────

def build_tts_text(evandjelje: dict, reading_number: int) -> str:
    if reading_number == 1:
        return evandjelje["tekst"]
    else:
        return f"Ponavljanje. {evandjelje['tekst']}"


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

def build_final_audio(reading_paths: list, target_ms: int) -> AudioSegment:
    """
    Spaja 3 čitanja s tišinom između, ukupno točno target_ms.
    Raspored: [tišina] čitanje1 [tišina] čitanje2 [tišina] čitanje3 [tišina]
    """
    segments = [AudioSegment.from_mp3(p) for p in reading_paths]
    total_reading_ms = sum(len(s) for s in segments)
    remaining_ms = target_ms - total_reading_ms

    if remaining_ms < 0:
        print("UPOZORENJE: Čitanja su duža od 10 min, nema tišine.")
        silence_ms = 1000
    else:
        # 4 bloka tišine: prije, između (×2), poslije
        silence_ms = remaining_ms // 4

    print(f"Trajanje čitanja: {total_reading_ms/1000:.1f}s")
    print(f"Tišina po bloku: {silence_ms/1000:.1f}s")

    final = AudioSegment.silent(duration=silence_ms)
    for i, seg in enumerate(segments):
        final += seg
        final += AudioSegment.silent(duration=silence_ms)

    # Fino podešavanje na točno 10 min
    if len(final) < target_ms:
        final += AudioSegment.silent(duration=target_ms - len(final))
    else:
        final = final[:target_ms]

    print(f"Ukupno trajanje: {len(final)/1000:.1f}s ({len(final)/60000:.2f} min)")
    return final


# ── Email ──────────────────────────────────────────────────────────────────────

def send_email(mp3_path: str, evandjelje: dict, recipient: str) -> None:
    today = datetime.date.today()
    subject = f"Evanđelje dana — {today.strftime('%d. %m. %Y.')} — {evandjelje['referenca']}"

    body = f"""Dobro jutro,

U prilogu je audio evanđelje za danas.

📖 {evandjelje['referenca']}
✝ {evandjelje['naslov']}

Čitanje je ponovljeno 3 puta unutar 10 minuta.

Lp,
Vaš automatski podsjetnik
"""

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
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Scrape
        url = get_today_url()
        evandjelje = scrape_evandjelje(url)

        # 2. Generiraj 3 TTS audio fajla
        reading_paths = []
        for i in range(1, 4):
            text = build_tts_text(evandjelje, i)
            path = os.path.join(tmpdir, f"reading_{i}.mp3")
            generate_tts(text, path)
            reading_paths.append(path)
            if i < 3:
                time.sleep(1)

        # 3. Spoji u 10-minutni audio
        final_audio = build_final_audio(reading_paths, TARGET_DURATION_MS)
        final_path = os.path.join(tmpdir, "evandjelje_final.mp3")
        final_audio.export(final_path, format="mp3", bitrate="128k")

        # 4. Pošalji mail
        send_email(final_path, evandjelje, RECIPIENT_EMAIL)

    print("Gotovo! ✓")


if __name__ == "__main__":
    main()
