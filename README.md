# 🎙️ Evanđelje Audio

Svaki dan u 02:00 scrapa evanđelje s [hilp.hr](https://hilp.hr/liturgija-dana/),  
generira 10-minutni audio (ElevenLabs TTS) i šalje ga mailom.

Audio format:
- Kratki uvod + čitanje evanđelja × 3
- Tišina između svakog čitanja
- Ukupno točno **10 minuta**

---

## 📋 Postavljanje (jednom)

### 1. Napravi GitHub repozitorij

- Idi na [github.com/new](https://github.com/new)
- Ime: `evandjelje-audio` (ili što god želiš)
- **Private** repozitorij (preporučeno)
- Uploadaj sve fajlove iz ovog paketa

### 2. ElevenLabs račun

1. Registriraj se na [elevenlabs.io](https://elevenlabs.io)
2. Idi na **Profile → API Key** i kopiraj key
3. Odaberi glas koji želiš:
   - Idi na **Voice Library**
   - Pretraži npr. "Croatian" ili odaberi neki od defaultnih
   - Kopiraj **Voice ID** (vidljiv u URL-u ili u detalju glasa)
   - Ako ne postaviš VOICE_ID, koristit će se default glas "Adam"

> **Napomena:** Besplatni plan ima ~10.000 znakova/mj.  
> Evanđelje ima ~500-800 znakova × 3 čitanja = ~2.000 znakova/dan.  
> Za svakodnevnu upotrebu preporučujem **Starter plan** (~$5/mj).

### 3. Gmail App Password

Gmail **ne dopušta** direktnu lozinku — trebaš App Password:

1. Idi na [myaccount.google.com/security](https://myaccount.google.com/security)
2. Uključi **2-Step Verification** (ako već nije)
3. Traži **App passwords** (na dnu stranice)
4. Odaberi: App = "Mail", Device = "Other" → upiši "GitHub Actions"
5. Kopiraj 16-znamenkasti kod (npr. `abcd efgh ijkl mnop`)

### 4. Postavi GitHub Secrets

U svom repozitoriju:  
**Settings → Secrets and variables → Actions → New repository secret**

Dodaj ove secretse:

| Naziv | Vrijednost |
|-------|-----------|
| `ELEVENLABS_API_KEY` | tvoj ElevenLabs API key |
| `ELEVENLABS_VOICE_ID` | ID glasa (opcionalno) |
| `GMAIL_USER` | `ivbpnv@gmail.com` |
| `GMAIL_APP_PASSWORD` | 16-znamenkasti app password |
| `RECIPIENT_EMAIL` | `ivan-os@live.com` |

### 5. Provjeri da radi

- Idi na **Actions** tab u svom repozitoriju
- Klikni na **"Evanđelje Audio — Dnevni mail"**
- Klikni **"Run workflow"** → **"Run workflow"**
- Prati log — trebao bi vidjeti scraping, TTS generiranje i slanje maila

---

## 🕐 Vremenska zona

Workflow se pokreće u **01:00 UTC** = **02:00 CET (zima)** / **03:00 CEST (ljeto)**.  
Ako želiš prilagoditi, uredi `cron` liniju u `.github/workflows/daily.yml`.

---

## 📁 Struktura fajlova

```
evandjelje-audio/
├── main.py                          # Glavna skripta
├── requirements.txt                 # Python paketi
├── README.md                        # Ove upute
└── .github/
    └── workflows/
        └── daily.yml                # GitHub Actions workflow
```

---

## 🔧 Česti problemi

**"Nije pronađeno evanđelje"** — hilp.hr je promijenio strukturu stranice. Provjeri URL format za taj dan.

**Gmail greška** — provjeri App Password, ne koristiti pravu lozinku.

**ElevenLabs greška** — provjeri API key i da imaš dovoljno kredita.
