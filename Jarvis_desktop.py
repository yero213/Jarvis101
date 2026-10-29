"""J.A.R.V.I.S. - Desktop UI (Tkinter)

Chat-interface voor de Jarvis-assistent, met dezelfde workspace als Jarvis.py.
Werkt met Ollama (lokaal) voor de LLM-antwoorden.

Gebruik:
    python Jarvis_desktop.py

Vereisten:
    pip install ollama
    (optioneel) google-auth google-auth-oauthlib google-api-python-client  voor Gmail/Drive
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from pathlib import Path

# ---------------------------------------------------------------------------
# Werkmap (zelfde sandbox als Jarvis.py)
# ---------------------------------------------------------------------------
WORKSPACE = Path.home() / "Jarvis" / "workspace"
WORKSPACE.mkdir(parents=True, exist_ok=True)

LLM_MODEL = "qwen2.5-coder:7b"
OLLAMA_HOST = "http://localhost:11434"

# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------
try:
    from ollama import Client as OllamaClient
    ollama_client = OllamaClient(host=OLLAMA_HOST)
except Exception:  # ollama niet geïnstalleerd of niet draaiend
    ollama_client = None

# ---------------------------------------------------------------------------
# Google OAuth helpers (zelfde scopespakket als Jarvis.py)
# ---------------------------------------------------------------------------
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _google_creds():
    """OAuth2 credentials voor Gmail en Drive."""
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
# Gmail / Drive (alleen als libraries geïnstalleerd zijn)
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
# Desktop UI
# ---------------------------------------------------------------------------
class JarvisDesktop(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("J.A.R.V.I.S. — Desktop")
        self.geometry("900x650")
        self.minsize(700, 500)

        self._setup_theme()
        self._build_layout()

        # Status controleren bij opstart
        self._check_ollama()
        self._refresh_files()

        # Geschiedenis voor de LLM
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ------------------------------------------------------------------
    # Opmaak
    # ------------------------------------------------------------------
    def _setup_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        # Donkere, britse assistent-kleuren
        self.configure(bg="#1e1e1e")
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabel", background="#1e1e1e", foreground="#d4d4d4", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 13, "bold"), foreground="#c7c7c7")
        style.configure("Status.TLabel", font=("Segoe UI", 9), foreground="#888888")
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure("Send.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", background="#2d2d2d", fieldbackground="#2d2d2d",
                        foreground="#d4d4d4", borderwidth=0)
        style.configure("Treeview.Heading", background="#3a3a3a", foreground="#c7c7c7",
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#3a7ca5")])

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self):
        # Hoofdcontainer
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        # ---- Sidebar: werkmap ----
        sidebar = ttk.Frame(container, width=220)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        sidebar.grid_propagate(False)

        ttk.Label(sidebar, text="Werkmap", style="Title.TLabel").pack(anchor="w", pady=(0, 6))

        self.file_list = tk.Listbox(
            sidebar, bg="#2d2d2d", fg="#d4d4d4", selectbackground="#3a7ca5",
            selectforeground="white", borderwidth=0, highlightthickness=0,
            font=("Consolas", 9), activestyle="none",
        )
        self.file_list.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.file_list.bind("<Double-Button-1>", self._on_file_double_click)

        btn_frame = ttk.Frame(sidebar)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Ververs", command=self._refresh_files).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3))
        ttk.Button(btn_frame, text="Open map", command=self._open_workspace).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0))

        # ---- Chatgebied ----
        chat_container = ttk.Frame(container)
        chat_container.grid(row=0, column=1, sticky="nsew")
        chat_container.columnconfigure(0, weight=1)
        chat_container.rowconfigure(0, weight=1)

        self.chat = scrolledtext.ScrolledText(
            chat_container, wrap=tk.WORD, bg="#252526", fg="#d4d4d4",
            insertbackground="#ffffff", selectbackground="#3a7ca5",
            borderwidth=0, highlightthickness=0, font=("Segoe UI", 11),
            padx=12, pady=12,
        )
        self.chat.grid(row=0, column=0, sticky="nsew")
        self.chat.configure(state=tk.DISABLED)

        # Chat-tags
        self.chat.tag_configure("jarvis", foreground="#569cd6", font=("Segoe UI", 11, "bold"))
        self.chat.tag_configure("user", foreground="#ce9178", font=("Segoe UI", 11, "bold"))
        self.chat.tag_configure("system", foreground="#888888", font=("Segoe UI", 9, "italic"))
        self.chat.tag_configure("error", foreground="#f48771")

        # ---- Inputbalk ----
        input_container = ttk.Frame(chat_container)
        input_container.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        input_container.columnconfigure(0, weight=1)

        self.entry = tk.Text(
            input_container, height=3, bg="#333333", fg="#ffffff",
            insertbackground="#ffffff", borderwidth=0, highlightthickness=1,
            highlightbackground="#444444", font=("Segoe UI", 10),
            padx=8, pady=6,
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Shift-Return>", lambda e: "break")  # Shift+Enter = nieuwe regel

        btns = ttk.Frame(input_container)
        btns.grid(row=0, column=1, sticky="ns")
        ttk.Button(btns, text="Verstuur", style="Send.TButton", command=self._send_message).pack(side=tk.RIGHT, padx=(0, 2))
        ttk.Button(btns, text="Wis", command=self._clear_chat).pack(side=tk.RIGHT)

        # ---- Statusbalk ----
        self.status_var = tk.StringVar(value="Klaar")
        status = ttk.Label(self, textvariable=self.status_var, style="Status.TLabel", anchor="w")
        status.pack(fill=tk.X, padx=10, pady=(4, 0))

        # Welkomstbericht
        self._append_chat("J.A.R.V.I.S.", "Goedendag, Sir. Hoe kan ik u van dienst zijn?", "jarvis")
        self._append_chat("Systeem", f"Werkmap: {WORKSPACE}", "system")

    # ------------------------------------------------------------------
    # Chat helpers
    # ------------------------------------------------------------------
    def _append_chat(self, sender: str, text: str, tag: str):
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{sender}: ", (tag, "bold" if tag in ("jarvis", "user") else ""))
        self.chat.insert(tk.END, text + "\n\n")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _set_status(self, text: str):
        self.status_var.set(text)
        self.update_idletasks()

    # ------------------------------------------------------------------
    # Acties
    # ------------------------------------------------------------------
    def _on_enter(self, event):
        # Gewone Enter = verstuur, Shift+Enter = nieuwe regel (afgehandeld via bind)
        self._send_message()
        return "break"

    def _send_message(self):
        user_text = self.entry.get("1.0", tk.END).strip()
        if not user_text:
            return
        self.entry.delete("1.0", tk.END)
        self._append_chat("Jij", user_text, "user")
        self._set_status("Jarvis denkt na...")
        threading.Thread(target=self._llm_reply, args=(user_text,), daemon=True).start()

    def _llm_reply(self, prompt: str):
        try:
            if ollama_client is None:
                self.after(0, lambda: self._append_chat("Systeem", "Ollama client niet beschikbaar. Installeer met: pip install ollama", "error"))
                self.after(0, lambda: self._set_status("Klaar"))
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
            self.after(0, lambda: self._set_status("Klaar"))
        except Exception as exc:
            self.after(0, lambda: self._append_chat("Systeem", f"Fout: {exc}", "error"))
            self.after(0, lambda: self._set_status("Klaar"))

    def _clear_chat(self):
        self.chat.configure(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.configure(state=tk.DISABLED)
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
        # Bestandsnaam eruit halen (voor mappen staat er een / achter)
        name = line.split(" (")[0].rstrip("/")
        if name.endswith("/"):
            self._refresh_files()  # map-dubbelklik: herladen (submap-navigatie later uitbreiden)
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
                    self.after(0, lambda: self._set_status("Ollama client niet geïnstalleerd"))
                    return
                tags = ollama_client.list()
                models = [m["model"] for m in tags.get("models", [])]
                available = any(LLM_MODEL in m for m in models)
                if available:
                    self.after(0, lambda: self._set_status(f"Ollama online — model {LLM_MODEL} klaar"))
                else:
                    self.after(0, lambda: self._set_status(f"Ollama online, maar {LLM_MODEL} niet gevonden (beschikbaar: {', '.join(models) or 'geen'})"))
            except Exception:
                self.after(0, lambda: self._set_status("Ollama niet bereikbaar op localhost:11434"))

        threading.Thread(target=check, daemon=True).start()


if __name__ == "__main__":
    app = JarvisDesktop()
    app.mainloop()
