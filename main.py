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
from bs4 import BeautifulSoup
from pydub import AudioSegment
from pydub.generators import Sine


# ── Konfiguracija (čita iz environment varijabli) ──────────────────────────────
ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Adam (default)

GMAIL_USER = os.environ["GMAIL_USER"]          # ivbpnv@gmail.com
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "ivan-os@live.com")

TARGET_DURATION_MS = 10 * 60 * 1000  # 10 minuta u milisekundama


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_today_url() -> str:
    """Gradi URL za današnji dan u formatu hilp.hr"""
    days_hr = {
        0: "ponedjeljak", 1: "utorak", 2: "srijeda",
        3: "cetvrtak", 4: "petak", 5: "subota", 6: "nedjelja"
    }
    today = datetime.date.today()
    day_name = days_hr[today.weekday()]
    date_str = today.strftime("%-d-%-m-%Y")  # npr. 4-3-2026
    return f"https://hilp.hr/liturgija-dana/{day_name}-{date_str}/"


def scrape_evandjelje(url: str) -> dict:
    """Scrapa stranicu i vraća dict s naslovom i tekstom evanđelja."""
    print(f"Scraping: {url}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Pronađi sekciju evanđelja
    evandjelje_data = {"naslov": "", "referenca": "", "tekst": ""}

    headings = soup.find_all(["h4", "h3", "h2"])
    evandjelje_heading = None
    for h in headings:
        if "Evanđelje" in h.get_text():
            evandjelje_heading = h
            break

    if not evandjelje_heading:
        raise ValueError("Nije pronađeno evanđelje na stranici!")

    # Referenca (npr. Mt 20,17-28) — odmah iza headinga
    ref_tag = evandjelje_heading.find_next_sibling()
    if ref_tag:
        evandjelje_data["referenca"] = ref_tag.get_text(strip=True)

    # Naslov evanđelja (sljedeći heading)
    naslov_tag = ref_tag.find_next_sibling() if ref_tag else None
    if naslov_tag:
        evandjelje_data["naslov"] = naslov_tag.get_text(strip=True)

    # Tekst evanđelja — skupi sve <p> tagove do sljedećeg heading-a
    tekst_dijelovi = []
    node = naslov_tag.find_next_sibling() if naslov_tag else evandjelje_heading.find_next_sibling()
    while node:
        if node.name in ["h4", "h3", "h2"]:
            break
        text = node.get_text(strip=True)
        if text:
            tekst_dijelovi.append(text)
        node = node.find_next_sibling()

    evandjelje_data["tekst"] = "\n".join(tekst_dijelovi)

    print(f"Pronađeno evanđelje: {evandjelje_data['referenca']} - {evandjelje_data['naslov']}")
    return evandjelje_data


def build_tts_text(evandjelje: dict, reading_number: int) -> str:
    """Gradi tekst za TTS za jedno čitanje."""
    if reading_number == 1:
        uvod = (
            f"Čitanje svetog Evanđelja po {evandjelje['referenca']}. "
            f"{evandjelje['naslov']}. "
        )
    else:
        uvod = f"Ponavljanje. {evandjelje['naslov']}. "

    return uvod + evandjelje["tekst"]


def generate_tts(text: str, output_path: str) -> None:
    """Poziva ElevenLabs API i sprema MP3."""
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


def make_silence(duration_ms: int) -> AudioSegment:
    """Vraća AudioSegment tišine zadane duljine."""
    return AudioSegment.silent(duration=duration_ms)


def build_final_audio(reading_paths: list, target_ms: int) -> AudioSegment:
    """
    Spaja 3 čitanja s tišinom između i paddingom na kraju
    kako bi ukupno trajanje bilo točno target_ms.
    """
    segments = [AudioSegment.from_mp3(p) for p in reading_paths]
    total_reading_ms = sum(len(s) for s in segments)

    # Koliko tišine rasporediti između čitanja (2 razmaka)
    # + malo na početku i kraju
    padding_start_ms = 2000   # 2 sec intro tišina
    padding_end_ms = 2000     # 2 sec outro tišina
    remaining_ms = target_ms - total_reading_ms - padding_start_ms - padding_end_ms

    if remaining_ms < 0:
        # Čitanja su duža od 10 min — bez tišine, samo spoji
        print("UPOZORENJE: Čitanja su duža od 10 min!")
        silence_between_ms = 1000
    else:
        silence_between_ms = remaining_ms // 2  # jednako raspoređena tišina

    print(f"Trajanje čitanja: {total_reading_ms/1000:.1f}s")
    print(f"Tišina između: {silence_between_ms/1000:.1f}s")

    final = make_silence(padding_start_ms)
    for i, seg in enumerate(segments):
        final += seg
        if i < len(segments) - 1:
            final += make_silence(silence_between_ms)
    final += make_silence(padding_end_ms)

    # Fino podešavanje na točno 10 min
    if len(final) < target_ms:
        final += make_silence(target_ms - len(final))
    else:
        final = final[:target_ms]

    print(f"Ukupno trajanje: {len(final)/1000:.1f}s ({len(final)/60000:.2f} min)")
    return final


def send_email(mp3_path: str, evandjelje: dict, recipient: str) -> None:
    """Šalje mail s MP3 attachmentom."""
    today = datetime.date.today()
    subject = f"Evanđelje dana — {today.strftime('%d. %m. %Y')} — {evandjelje['referenca']}"

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

    # Attach MP3
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
                time.sleep(1)  # mali delay između API poziva

        # 3. Spoji u 10-minutni audio
        final_audio = build_final_audio(reading_paths, TARGET_DURATION_MS)
        final_path = os.path.join(tmpdir, "evandjelje_final.mp3")
        final_audio.export(final_path, format="mp3", bitrate="128k")

        # 4. Pošalji mail
        send_email(final_path, evandjelje, RECIPIENT_EMAIL)

    print("Gotovo! ✓")


if __name__ == "__main__":
    main()
