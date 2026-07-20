#!/usr/bin/env python3
"""ElevenLabs TTS renderer for the Chain Codex pages.

Reads /var/www/23skidoo.info/codex/tts-pages.json (produced by build_ereader.py),
renders any missing MP3s into /var/www/23skidoo.info/static/tts/{key}.mp3.

Respects a monthly char budget so Free tier (10k/mo) lasts the month.
Skips silently if no API key is configured."""
import os, json, time, urllib.request, urllib.error, re

def humanize(text):
    """Insert <break> tags so sentence pauses are roughly twice as long.
    Only applied for the ElevenLabs API; browser SpeechSynthesis fallback
    reads the plain manifest text without tags."""
    # Sentence-end punctuation followed by whitespace
    text = re.sub(r"([.!?])(\s+)", r"\1 <break time=\"0.5s\" />\2", text)
    # Trailing punctuation at end of buffer
    text = re.sub(r"([.!?])$", r"\1 <break time=\"0.5s\" />", text)
    # Paragraph breaks: longer beat
    text = text.replace("\n\n", "\n\n<break time=\"1.0s\" />\n\n")
    return text

from pathlib import Path

STATE_DIR = Path('/home/btcbob/codex')   # runtime state + secrets (gitignored by location)
ENV     = STATE_DIR / 'eleven.env'
MAN     = Path('/var/www/23skidoo.info/codex/tts-pages.json')
OUTDIR  = Path('/var/www/23skidoo.info/static/tts')
STATE   = STATE_DIR / 'tts_state.json'
LOG     = STATE_DIR / 'tts_cron.log'

DEFAULT_VOICE = 'pNInz6obpgDQGcFmaJgB'   # Adam, deep male, Free-tier eligible
DEFAULT_MODEL = 'eleven_multilingual_v2'
SETTINGS      = {'stability': 0.6, 'similarity_boost': 0.75, 'style': 0.4, 'use_speaker_boost': True}

def load_env():
    e = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            k, v = line.split('=', 1)
            e[k.strip()] = v.strip().strip('"').strip("'")
    return e

def render_to_mp3(text, voice, model, api_key):
    body = json.dumps({'text': humanize(text), 'model_id': model, 'voice_settings': SETTINGS}).encode()
    req = urllib.request.Request(
        f'https://api.elevenlabs.io/v1/text-to-speech/{voice}',
        method='POST', data=body,
        headers={'xi-api-key': api_key, 'Content-Type': 'application/json', 'Accept': 'audio/mpeg'},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()

def main():
    env = load_env()
    key = env.get('XI_API_KEY', '').strip()
    if not key or 'paste' in key.lower() or key.startswith('sk_xxx'):
        print('no API key configured — skipping (paste into', ENV, ')'); return 0
    voice  = env.get('XI_VOICE_ID', DEFAULT_VOICE)
    model  = env.get('XI_MODEL',    DEFAULT_MODEL)
    budget = int(env.get('XI_MONTHLY_CHARS', '9500'))

    if not MAN.exists():
        print('no manifest:', MAN); return 1
    pages = json.loads(MAN.read_text())
    OUTDIR.mkdir(parents=True, exist_ok=True)

    month = time.strftime('%Y-%m')
    state = {'month': month, 'chars_used': 0}
    if STATE.exists():
        try: state = json.loads(STATE.read_text())
        except: pass
    if state.get('month') != month:
        state = {'month': month, 'chars_used': 0}

    rendered = 0
    for p in pages:
        text = (p.get('text') or '').strip()
        if not text: continue
        out = OUTDIR / f'{p["key"]}.mp3'
        if out.exists() and out.stat().st_size > 0: continue
        n = len(text)
        if state['chars_used'] + n > budget:
            print(f'month budget reached ({state["chars_used"]}/{budget}); stopping')
            break
        print(f'rendering {p["key"]} book={p["book"]} page={p["page"]} chars={n}')
        try:
            mp3 = render_to_mp3(text, voice, model, key)
        except urllib.error.HTTPError as e:
            print(f'API error {e.code}: {e.read()[:200]!r}'); break
        except Exception as e:
            print(f'render failed: {e}'); break
        tmp = out.with_suffix('.mp3.tmp')
        tmp.write_bytes(mp3)
        os.replace(tmp, out)
        state['chars_used'] += n
        rendered += 1
        time.sleep(3)

    state['last_run'] = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
    STATE.write_text(json.dumps(state))
    pct = (100 * state["chars_used"] / budget) if budget else 0
    print(f'BUDGET {month} rendered={rendered} used={state["chars_used"]}/{budget} ({pct:.1f}%)')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
