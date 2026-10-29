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
