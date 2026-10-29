# Session Log – Jarvis

## Werkafspraken (elke sessie)

1. **Start van de sessie:** eerst `git pull origin main` om de laatste versie van GitHub op te halen.
2. **Tijdens de sessie:** werkzaamheden uitvoeren.
3. **Einde van de sessie:**
   - Korte samenvatting schrijven in dit bestand (onderstaande sectie "Sessies").
   - `git add .` (secrets blijven buiten via `.gitignore`).
   - `git commit -m "...`
   - `git push origin main`

---

## Sessies

### Sessie 1 – 29-10-2026
- GitHub-repo aangemaakt: https://github.com/yero213/Jarvis101
- Eerste commit gepusht naar branch `main`
- Bestanden toegevoegd: `.gitignore`, `.env.example`, `Jarvis.py`, `Jarvis_debug.py`, `Jarvis_gemini.py`, `run.bat`
- Secrets bewust uitgesloten: `.env`, `credentials.json.json`, `.venv/`, `__pycache__/`, `kokoro-v1.0.onnx`, `voices-v1.0.bin`, `projectstatus-*.json`
- Remote ingesteld op `https://github.com/yero213/Jarvis101.git` (token verwijderd uit remote-config)

### Sessie 2 – 29-10-2026
- `SESSION_LOG.md` aangemaakt met werkafspraken per sessie (start: pull, einde: samenvatting + commit + push)
- Git pull gedaan: repo was up to date
- Alles gecommit en gepusht naar `main` op https://github.com/yero213/Jarvis101
- Sessie afgerond

### Sessie 3 – 29-10-2026
- `Jarvis.py` uitgebreid met Home Assistant & Umbrel tools:
  - `ha_states(entity_id)` — haal HA entiteitstatus op
  - `ha_service(domain, service, entity_id)` — roep HA service aan (bijv. licht aan/uit)
  - `umbrel_ssh(command)` — voer commando uit op Umbrel via SSH (paramiko)
- De 3 nieuwe tools geregistreerd in `TOOLS` dictionary
- `.env.example` bijgewerkt met HA_URL, HA_TOKEN, UMBREL_HOST, UMBREL_USER, UMBREL_SSH_KEY, UMBREL_PASSWORD
- Alles gecommit en gepusht naar `main` op https://github.com/yero213/Jarvis101
- `.env` (met API-key) blijft lokaal, staat in `.gitignore`
- Sessie afgerond

### Sessie 4 – 29-10-2026
- `credentials.json.json` hernoemd naar `credentials.json` (Google OAuth client secrets)
- Google API libraries geïnstalleerd: google-auth, google-auth-oauthlib, google-auth-httplib2, google-api-python-client
- Gmail & Drive OAuth flow getest: verbinding werkt, 3 recente berichten opgehaald
- Token opgeslagen in `~/.jarvis_token.json` (buiten projectmap, nooit naar GitHub)
- `credentials.json` staat in `.gitignore` (via `credentials*.json`)
- SESSION_LOG.md gecommit en gepusht naar `main` op https://github.com/yero213/Jarvis101
- Sessie afgerond

### Sessie 5 – 29-10-2026
- `Jarvis_desktop.py` aangemaakt: Tkinter desktop UI voor Jarvis
  - Chat-interface met Ollama LLM (qwen2.5-coder:7b)
  - Werkmap-bestandbrowser (list, lezen via dubbelklik)
  - Statusbalk (Ollama online/offline, model beschikbaar)
  - Gmail & Drive tools geïntegreerd (gmail_list, gmail_send, drive_list)
  - Donkere "British assistant"-thema
  - Zelfde WORKSPACE als Jarvis.py (~//Jarvis/workspace)
- Alles gecommit en gepusht naar `main` op https://github.com/yero213/Jarvis101
- Sessie afgerond
