"""J.A.R.V.I.S. — Iron Man geïnspireerde desktop UI (Tkinter)

Holografische HUD-stijl chat-interface met Ollama LLM.
"""
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuratie
# ---------------------------------------------------------------------------
WORKSPACE = Path.home() / "Jarvis" / "workspace"
WORKSPACE.mkdir(parents=True, exist_ok=True)

LLM_MODEL = "qwen2.5-coder:7b"
OLLAMA_HOST = "http://localhost:11434"

# Kleurenpalet (Iron Man / Jarvis hologram)
BG_COLOR = "#050508"           # Diepzwart / nachtblauw
PANEL_COLOR = "#0a0a12"       # Panel donker
ACCENT_COLOR = "#00e5ff"      # Cyaan neon
ACCENT_DIM = "#007a9e"        # Gedimd cyaan
TEXT_COLOR = "#e0e0e0"        # Lichtgrijs
DANGER_COLOR = "#ff4444"      # Rood voor fouten
OK_COLOR = "#44ff88"          # Groen voor online

# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------
try:
    from ollama import Client as OllamaClient
    ollama_client = OllamaClient(host=OLLAMA_HOST)
except Exception:
    ollama_client = None

# ---------------------------------------------------------------------------
# Google OAuth helpers (zelfde als Jarvis.py)
# ---------------------------------------------------------------------------
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _google_creds():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    token_file = Path.home() / ".jarvis_token.json"
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), GOOGLE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            credentials_file = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json())
    return creds


# ---------------------------------------------------------------------------
# Bestandstools (zelfde workspace-logica als Jarvis.py)
# ---------------------------------------------------------------------------
TEXT_LIKE = {
    ".txt", ".md", ".csv", ".json", ".py", ".html", ".xml", ".yaml", ".yml",
    ".log", ".ini", ".toml", ".js", ".css", ".sh", ".tsv",
}
MAX_READ_CHARS = 6000


def _safe_path(name: str) -> Path:
    root = WORKSPACE.resolve()
    p = (root / name).resolve()
    if p != root and root not in p.parents:
        raise ValueError("That path is outside the workspace.")
    return p


def _truncate(text: str) -> str:
    if len(text) > MAX_READ_CHARS:
        return text[:MAX_READ_CHARS] + f"\n[...truncated, file has {len(text)} characters in total]"
    return text


def list_files(folder: str = "") -> str:
    base = _safe_path(folder)
    if not base.is_dir():
        return f"Folder not found: {folder}"
    lines = []
    for p in sorted(base.rglob("*"))[:100]:
        if p.name.startswith("."):
            continue
        rel = p.relative_to(WORKSPACE.resolve())
        lines.append(f"{rel}/" if p.is_dir() else f"{rel} ({p.stat().st_size} bytes)")
    return "\n".join(lines) if lines else "The workspace is empty."


def read_file(filename: str) -> str:
    p = _safe_path(filename)
    if not p.is_file():
        return f"File not found: {filename}."
    ext = p.suffix.lower()
    if ext in TEXT_LIKE or ext == "":
        return _truncate(p.read_text(encoding="utf-8", errors="replace"))
    return f"I can't read {ext} files yet."


def write_file(filename: str, content: str, overwrite: bool = False) -> str:
    p = _safe_path(filename)
    ext = p.suffix.lower()
    if p.exists() and not overwrite:
        return f"{filename} already exists. Use overwrite=True to replace."
    p.parent.mkdir(parents=True, exist_ok=True)
    if ext in TEXT_LIKE or ext == "":
        p.write_text(content, encoding="utf-8")
    else:
        return f"I can't write {ext} files yet."
    return f"Saved {filename}."


def append_file(filename: str, content: str) -> str:
    p = _safe_path(filename)
    if p.suffix.lower() not in TEXT_LIKE and p.suffix != "":
        return "Appending only works on plain text files."
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(("\n" if p.exists() and p.stat().st_size else "") + content)
    return f"Added to {filename}."


# ---------------------------------------------------------------------------
# Gmail / Drive
# ---------------------------------------------------------------------------
def gmail_list(query: str = "is:unread", max_results: int = 5) -> str:
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=_google_creds())
        result = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = result.get("messages", [])
        if not messages:
            return "Geen e-mails gevonden."
        lines = []
        for m in messages:
            msg = service.users().messages().get(userId="me", id=m["id"], format="metadata").execute()
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
            lines.append(
                f"- {headers.get('Date','?')}: {headers.get('Subject','(geen onderwerp)')} "
                f"(van {headers.get('From','?')})"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Fout bij Gmail: {e}"


def gmail_send(to: str, subject: str, body: str) -> str:
    try:
        import base64
        from email.mime.text import MIMEText
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=_google_creds())
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"E-mail verzonden naar {to}."
    except Exception as e:
        return f"Fout bij verzenden: {e}"


def drive_list(folder_id: str = "root", max_results: int = 10) -> str:
    try:
        from googleapiclient.discovery import build
        service = build("drive", "v3", credentials=_google_creds())
        result = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime)",
        ).execute()
        files = result.get("files", [])
        if not files:
            return "Drive-map is leeg."
        return "\n".join(f"- {f['name']} ({f['mimeType']})" for f in files)
    except Exception as e:
        return f"Fout bij Drive: {e}"


# ---------------------------------------------------------------------------
# Systeempromptuk
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., a sophisticated, dry-witted British AI assistant. "
    "Your replies are spoken aloud, so talk like a person, not a document: "
    "short sentences, natural phrasing, contractions where fitting, "
    "no lists, no markdown, no emojis, no code unless asked. "
    "Keep answers to one to three sentences unless more is needed. "
    "Address the user as Sir. "
)


# ---------------------------------------------------------------------------
# HUD Canvas helpers
# ---------------------------------------------------------------------------
def draw_corner(canvas, x, y, w, h, size=20, color=ACCENT_COLOR, width=2):
    """Teken HUD-hoekjes (Iron Man stijl)."""
    # Top-left
    canvas.create_line(x, y + size, x, y, width=width, fill=color, tags="hud")
    canvas.create_line(x, y, x + size, y, width=width, fill=color, tags="hud")
    # Top-right
    canvas.create_line(x + w - size, y, x + w, y, width=width, fill=color, tags="hud")
    canvas.create_line(x + w, y, x + w, y + size, width=width, fill=color, tags="hud")
    # Bottom-left
    canvas.create_line(x, y + h - size, x, y + h, width=width, fill=color, tags="hud")
    canvas.create_line(x, y + h, x + size, y + h, width=width, fill=color, tags="hud")
    # Bottom-right
    canvas.create_line(x + w - size, y + h, x + w, y + h, width=width, fill=color, tags="hud")
    canvas.create_line(x + w, y + h - size, x + w, y + h, width=width, fill=color, tags="hud")


# ---------------------------------------------------------------------------
# Hoofdapplicatie
# ---------------------------------------------------------------------------
class JarvisDesktop(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("J.A.R.V.I.S. — HUD Interface")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        self.configure(bg=BG_COLOR)

        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._anim_running = True
        self._build_hud()
        self._start_hud_animation()

        # Startup checks
        self.after(500, self._check_ollama)
        self.after(800, self._refresh_files)

        self._append_chat("J.A.R.V.I.S.", "Systems online, Sir. HUD interface active.", "jarvis")
        self._append_chat("Systeem", f"Werkmap: {WORKSPACE}", "system")

    # ------------------------------------------------------------------
    # HUD layout
    # ------------------------------------------------------------------
    def _build_hud(self):
        # Hoofdcontainer met donkere achtergrond
        self.container = tk.Frame(self, bg=BG_COLOR)
        self.container.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Bovenste HUD-balk
        self.top_bar = tk.Frame(self.container, bg=PANEL_COLOR, height=60)
        self.top_bar.pack(fill=tk.X, pady=(0, 4))
        self.top_bar.pack_propagate(False)

        # Titel links
        self.title_label = tk.Label(
            self.top_bar, text="J.A.R.V.I.S.  v1.0", bg=PANEL_COLOR,
            fg=ACCENT_COLOR, font=("Courier New", 14, "bold"),
        )
        self.title_label.pack(side=tk.LEFT, padx=16, pady=15)

        # Status rechts
        self.status_label = tk.Label(
            self.top_bar, text="STANDBY", bg=PANEL_COLOR, fg=ACCENT_DIM,
            font=("Courier New", 11, "bold"),
        )
        self.status_label.pack(side=tk.RIGHT, padx=20, pady=15)

        # Hoekjes om de top bar
        self.top_canvas = tk.Canvas(
            self.top_bar, height=60, bg=PANEL_COLOR, highlightthickness=0,
        )
        self.top_canvas.place(x=0, y=0, relwidth=1.0)

        # Hoofdinhoud: links bestandbrowser, rechts chat
        self.content = tk.Frame(self.container, bg=BG_COLOR)
        self.content.pack(fill=tk.BOTH, expand=True)
        self.content.columnconfigure(1, weight=1)
        self.content.rowconfigure(0, weight=1)

        # ---- Sidebar: werkmap ----
        self.sidebar = tk.Frame(self.content, bg=PANEL_COLOR, width=260)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.sidebar.grid_propagate(False)

        self.sidebar_canvas = tk.Canvas(
            self.sidebar, bg=PANEL_COLOR, highlightthickness=0,
        )
        self.sidebar_canvas.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        tk.Label(
            self.sidebar, text="WERKMAP", bg=PANEL_COLOR, fg=ACCENT_COLOR,
            font=("Courier New", 10, "bold"),
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self.file_list = tk.Listbox(
            self.sidebar, bg=BG_COLOR, fg=TEXT_COLOR, selectbackground=ACCENT_COLOR,
            selectforeground="#000000", borderwidth=0, highlightthickness=0,
            font=("Consolas", 9), activestyle="none", highlightcolor=ACCENT_COLOR,
        )
        self.file_list.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.file_list.bind("<Double-Button-1>", self._on_file_double_click)

        btn_frame = tk.Frame(self.sidebar, bg=PANEL_COLOR)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 10))
        tk.Button(
            btn_frame, text="Ververs", bg=ACCENT_COLOR, fg="#000000",
            font=("Courier New", 9, "bold"), borderwidth=0,
            command=self._refresh_files,
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        tk.Button(
            btn_frame, text="Map", bg=PANEL_COLOR, fg=ACCENT_COLOR,
            font=("Courier New", 9, "bold"), borderwidth=1,
            highlightbackground=ACCENT_COLOR, command=self._open_workspace,
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))

        # ---- Chat gebied ----
        self.chat_container = tk.Frame(self.content, bg=BG_COLOR)
        self.chat_container.grid(row=0, column=1, sticky="nsew")
        self.chat_container.columnconfigure(0, weight=1)
        self.chat_container.rowconfigure(0, weight=1)

        # Chat canvas met HUD-lijst
        self.chat_canvas = tk.Canvas(
            self.chat_container, bg=BG_COLOR, highlightthickness=0,
        )
        self.chat_canvas.grid(row=0, column=0, sticky="nsew")

        # Scrollbare chat binnen canvas
        self.chat_frame = tk.Frame(self.chat_canvas, bg=BG_COLOR)
        self.chat_window = self.chat_canvas.create_window(
            (0, 0), window=self.chat_frame, anchor="nw", tags="chat_frame"
        )
        self.chat_canvas.bind("<Configure>", self._on_chat_configure)
        self.chat_frame.bind("<Configure>", lambda e: self.chat_canvas.configure(
            scrollregion=self.chat_canvas.bbox("all")
        ))

        # ---- Inputbalk ----
        self.input_bar = tk.Frame(self.container, bg=PANEL_COLOR, height=70)
        self.input_bar.pack(fill=tk.X, pady=(4, 0))
        self.input_bar.pack_propagate(False)

        self.entry = tk.Text(
            self.input_bar, height=3, bg=BG_COLOR, fg=TEXT_COLOR,
            insertbackground=ACCENT_COLOR, borderwidth=0, highlightthickness=1,
            highlightbackground=ACCENT_DIM, highlightcolor=ACCENT_COLOR,
            font=("Consolas", 11), padx=12, pady=10,
        )
        self.entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=12, pady=10)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Shift-Return>", lambda e: "break")

        self.send_btn = tk.Button(
            self.input_bar, text="SEND", bg=ACCENT_COLOR, fg="#000000",
            font=("Courier New", 10, "bold"), borderwidth=0,
            command=self._send_message,
        )
        self.send_btn.pack(side=tk.RIGHT, padx=12, pady=12)

        # Onderste statusbalk
        self.bottom_bar = tk.Frame(self.container, bg=PANEL_COLOR, height=30)
        self.bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.bottom_bar.pack_propagate(False)

        self.bottom_status = tk.Label(
            self.bottom_bar, text="READY", bg=PANEL_COLOR, fg=ACCENT_DIM,
            font=("Courier New", 9),
        )
        self.bottom_status.pack(side=tk.LEFT, padx=12, pady=6)

        self.ollama_status = tk.Label(
            self.bottom_bar, text="OLLAMA: --", bg=PANEL_COLOR, fg=ACCENT_DIM,
            font=("Courier New", 9),
        )
        self.ollama_status.pack(side=tk.RIGHT, padx=12, pady=6)

    # ------------------------------------------------------------------
    # HUD animatie
    # ------------------------------------------------------------------
    def _start_hud_animation(self):
        if not self._anim_running:
            return
        self._draw_hud_elements()
        self.after(100, self._start_hud_animation)

    def _draw_hud_elements(self):
        # Top bar hoekjes + scanning lines
        self.top_canvas.delete("hud")
        w = self.top_canvas.winfo_width()
        h = self.top_canvas.winfo_height()
        if w < 10 or h < 10:
            return
        c = ACCENT_COLOR
        draw_corner(self.top_canvas, 0, 0, w, h, size=24, color=c, width=2)

        # Scanning lijn die beweegt
        t = time.time() * 3
        y = int((math.sin(t) + 1) / 2 * (h - 4)) + 2
        self.top_canvas.create_line(4, y, w - 4, y, fill=c, width=1, tags="hud")

        # Sidebar hoekjes
        self.sidebar_canvas.delete("hud")
        sw = self.sidebar_canvas.winfo_width()
        sh = self.sidebar_canvas.winfo_height()
        if sw > 10 and sh > 10:
            draw_corner(self.sidebar_canvas, 0, 0, sw, sh, size=16, color=c, width=1)

    # ------------------------------------------------------------------
    # Chat helpers
    # ------------------------------------------------------------------
    def _on_chat_configure(self, event):
        self.chat_canvas.itemconfig(self.chat_window, width=event.width)

    def _append_chat(self, sender: str, text: str, tag: str):
        bubble = tk.Frame(self.chat_frame, bg=BG_COLOR)
        bubble.pack(fill=tk.X, padx=16, pady=(6, 2), anchor="e" if tag == "user" else "w")

        # Naamlabel
        name_color = ACCENT_COLOR if tag == "jarvis" else TEXT_COLOR
        name_lbl = tk.Label(
            bubble, text=sender, bg=BG_COLOR, fg=name_color,
            font=("Courier New", 9, "bold"), anchor="w",
        )
        name_lbl.pack(fill=tk.X)

        # Tekstbal
        bubble_bg = PANEL_COLOR if tag == "jarvis" else "#12121a"
        text_lbl = tk.Label(
            bubble, text=text, bg=bubble_bg, fg=TEXT_COLOR,
            font=("Consolas", 10), anchor="w", justify=tk.LEFT,
            padx=12, pady=10, wraplength=700,
        )
        text_lbl.pack(fill=tk.X, pady=(2, 0))

        # Hoekjes om de bubble
        cb = tk.Canvas(bubble, height=4, bg=BG_COLOR, highlightthickness=0)
        cb.pack(fill=tk.X)
        cb.create_line(0, 2, 120, 2, fill=ACCENT_COLOR, width=1)
        cb.create_line(580, 2, 700, 2, fill=ACCENT_COLOR, width=1)

        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)

    def _set_status(self, text: str, color=ACCENT_COLOR):
        self.status_label.config(text=text, fg=color)
        self.bottom_status.config(text=text, fg=color)

    # ------------------------------------------------------------------
    # Acties
    # ------------------------------------------------------------------
    def _on_enter(self, event):
        self._send_message()
        return "break"

    def _send_message(self):
        user_text = self.entry.get("1.0", tk.END).strip()
        if not user_text:
            return
        self.entry.delete("1.0", tk.END)
        self._append_chat("Jij", user_text, "user")
        self._set_status("PROCESSING...", ACCENT_COLOR)
        threading.Thread(target=self._llm_reply, args=(user_text,), daemon=True).start()

    def _llm_reply(self, prompt: str):
        try:
            if ollama_client is None:
                self.after(0, lambda: self._append_chat("Systeem", "Ollama client niet beschikbaar. Installeer met: pip install ollama", "error"))
                self.after(0, lambda: self._set_status("ERROR", DANGER_COLOR))
                return

            self.history.append({"role": "user", "content": prompt})

            response = ollama_client.chat(
                model=LLM_MODEL,
                messages=self.history,
                stream=False,
            )
            reply = response["message"]["content"]
            self.history.append({"role": "assistant", "content": reply})

            self.after(0, lambda: self._append_chat("J.A.R.V.I.S.", reply, "jarvis"))
            self.after(0, lambda: self._set_status("ONLINE", OK_COLOR))
        except Exception as exc:
            self.after(0, lambda: self._append_chat("Systeem", f"Fout: {exc}", "error"))
            self.after(0, lambda: self._set_status("ERROR", DANGER_COLOR))

    def _clear_chat(self):
        for widget in self.chat_frame.winfo_children():
            widget.destroy()
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._append_chat("J.A.R.V.I.S.", "Chat gewist, Sir. Hoe kan ik u helpen?", "jarvis")

    # ------------------------------------------------------------------
    # Werkmap
    # ------------------------------------------------------------------
    def _refresh_files(self):
        self.file_list.delete(0, tk.END)
        try:
            result = list_files("")
            for line in result.splitlines():
                self.file_list.insert(tk.END, line)
        except Exception as exc:
            self.file_list.insert(tk.END, f"Fout: {exc}")

    def _on_file_double_click(self, event):
        selection = self.file_list.curselection()
        if not selection:
            return
        line = self.file_list.get(selection[0])
        name = line.split(" (")[0].rstrip("/")
        if name.endswith("/"):
            self._refresh_files()
            return
        try:
            content = read_file(name)
            self._append_chat("Bestand", f"{name}\n{content}", "system")
        except Exception as exc:
            messagebox.showerror("Fout", str(exc))

    def _open_workspace(self):
        try:
            if sys.platform == "darwin":
                os.system(f'open "{WORKSPACE}"')
            elif sys.platform == "win32":
                os.startfile(str(WORKSPACE))  # type: ignore[attr-defined]
            else:
                os.system(f'xdg-open "{WORKSPACE}"')
        except Exception as exc:
            messagebox.showerror("Fout", str(exc))

    # ------------------------------------------------------------------
    # Ollama status
    # ------------------------------------------------------------------
    def _check_ollama(self):
        def check():
            try:
                if ollama_client is None:
                    self.after(0, lambda: self.ollama_status.config(text="OLLAMA: OFF", fg=DANGER_COLOR))
                    self.after(0, lambda: self._set_status("Ollama niet geïnstalleerd", DANGER_COLOR))
                    return
                tags = ollama_client.list()
                models = [m["model"] for m in tags.get("models", [])]
                available = any(LLM_MODEL in m for m in models)
                if available:
                    self.after(0, lambda: self.ollama_status.config(text=f"OLLAMA: {LLM_MODEL}", fg=OK_COLOR))
                    self.after(0, lambda: self._set_status("SYSTEMS ONLINE", OK_COLOR))
                else:
                    self.after(0, lambda: self.ollama_status.config(text="OLLAMA: MODEL MISSING", fg=DANGER_COLOR))
                    self.after(0, lambda: self._set_status(f"Model {LLM_MODEL} niet gevonden", DANGER_COLOR))
            except Exception:
                self.after(0, lambda: self.ollama_status.config(text="OLLAMA: OFFLINE", fg=DANGER_COLOR))
                self.after(0, lambda: self._set_status("Ollama niet bereikbaar", DANGER_COLOR))

        threading.Thread(target=check, daemon=True).start()

    def destroy(self):
        self._anim_running = False
        super().destroy()


import math  # noqa: E402  (nodig voor de HUD-animatie)

if __name__ == "__main__":
    app = JarvisDesktop()
    app.mainloop()
