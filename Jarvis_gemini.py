"""J.A.R.V.I.S. - Gemini Native Audio versie (naast de lokale pipeline).

Verschil met Jarvis.py:
- Jarvis.py           : Whisper (STT) + Ollama (LLM) + Kokoro (TTS), alles lokaal, wake-word standby.
- Jarvis_gemini.py    : Gemini 2.5 Flash Native Audio via Google AI Studio Live API.
                        Spraak-in -> spraak-uit in één sessie, VAD + onderbreken regelt Google.
                        Workspace-tools blijven werken via function calling.

Gebruik:
    .venv/Scripts/python.exe -m pip install google-genai python-dotenv
    zet GEMINI_API_KEY in .env (zie .env.example)
    .venv/Scripts/python.exe Jarvis_gemini.py

Je lokale Jarvis.py blijft ongewijzigd als offline fallback.
"""
import asyncio
import csv
import io
import os
import queue
import shutil
import sys
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd

# --- .env laden (zonder harde dependency op python-dotenv) ---
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except ImportError:
    env_file = Path(__file__).with_name(".env")
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

# --- Instellingen ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview-09-2025")
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Charon")  # Puck, Charon, Kore, Fenrir, Aoede, ...
LANGUAGE_NOTE = "British English"

SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., a sophisticated, dry-witted British AI assistant. "
    "Your replies are spoken aloud, so talk like a person, not a document: "
    "short sentences, natural phrasing, contractions where fitting, "
    "no lists, no markdown, no emojis, no code unless asked. "
    "Keep answers to one to three sentences unless more is needed. "
    "Address the user as Sir. "
    "You can list, read, write and append to files in your workspace using the provided tools. "
    "If you are unsure of a file name, call list_files first. "
    "Never claim you read or wrote a file unless the tool result confirms it. "
    "When you summarise a file, speak the gist in a few sentences instead of reading it out."
)

# --- Bestanden (zelfde sandbox als Jarvis.py) ---
WORKSPACE = Path.home() / "Jarvis" / "workspace"
MAX_READ_CHARS = 6000
WORKSPACE.mkdir(parents=True, exist_ok=True)
TEXT_LIKE = {".txt", ".md", ".csv", ".json", ".py", ".html", ".xml", ".yaml", ".yml",
             ".log", ".ini", ".toml", ".js", ".css", ".sh", ".tsv"}


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
        return f"File not found: {filename}. Use list_files to see what exists."
    ext = p.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        pages = [(page.extract_text() or "") for page in PdfReader(str(p)).pages]
        text = "\n\n".join(f"[page {i + 1}]\n{t}" for i, t in enumerate(pages))
        return _truncate(text) if text.strip() else "This PDF has no extractable text (it may be a scan)."
    if ext == ".docx":
        from docx import Document
        doc = Document(str(p))
        parts = [para.text for para in doc.paragraphs if para.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        return _truncate("\n".join(parts))
    if ext in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook
        wb = load_workbook(str(p), data_only=True, read_only=True)
        try:
            out = []
            for ws in wb.worksheets:
                out.append(f"[sheet: {ws.title}]")
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if i >= 200:
                        out.append("[...more rows]")
                        break
                    out.append(" | ".join("" if c is None else str(c) for c in row))
            return _truncate("\n".join(out))
        finally:
            wb.close()
    if ext in TEXT_LIKE or ext == "":
        return _truncate(p.read_text(encoding="utf-8", errors="replace"))
    return f"I can't read {ext} files yet."


def write_file(filename: str, content: str, overwrite: bool = False) -> str:
    p = _safe_path(filename)
    if not filename.strip() or p.is_dir():
        return "Give a valid file name, not an empty name or folder."
    ext = p.suffix.lower()
    if p.exists() and p.is_file():
        if not overwrite:
            return f"{filename} already exists. Ask the user whether to overwrite it or use another name."
        shutil.copy2(p, p.with_name(p.name + ".bak"))
    elif p.exists():
        return f"{filename} is not a regular file."
    if len(content) > 200_000:
        return "That content is too large (>200k chars). Write a shorter version."
    p.parent.mkdir(parents=True, exist_ok=True)
    if ext == ".docx":
        from docx import Document
        doc = Document()
        for line in content.splitlines():
            doc.add_paragraph(line)
        doc.save(str(p))
    elif ext == ".xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        for row in csv.reader(io.StringIO(content)):
            ws.append(row)
        wb.save(str(p))
    elif ext in TEXT_LIKE or ext == "":
        p.write_text(content, encoding="utf-8")
    else:
        return f"I can't write {ext} files yet."
    return f"Saved {filename}."


def append_file(filename: str, content: str) -> str:
    p = _safe_path(filename)
    if p.suffix.lower() not in TEXT_LIKE and p.suffix != "":
        return "Appending only works on plain text files. Use write_file for docx or xlsx."
    needs_newline = p.is_file() and p.stat().st_size > 0
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(("\n" if needs_newline else "") + content)
    return f"Added to {filename}."


TOOLS = {"list_files": list_files, "read_file": read_file,
         "write_file": write_file, "append_file": append_file}

# --- Gemini function declarations (zelfde tools, ander jasje) ---
FUNCTION_DECLARATIONS = [
    {"name": "list_files",
     "description": "List files and folders in the workspace or a subfolder.",
     "parameters": {"type": "OBJECT",
                    "properties": {"folder": {"type": "STRING",
                                              "description": "Optional subfolder, empty for top level."}}}},
    {"name": "read_file",
     "description": "Read a file from the workspace (text, pdf, docx, xlsx).",
     "parameters": {"type": "OBJECT",
                    "properties": {"filename": {"type": "STRING",
                                                "description": "Relative path like notes.txt"}},
                    "required": ["filename"]}},
    {"name": "write_file",
     "description": "Create a file. For xlsx/csv give CSV text, one row per line. Only overwrite when user confirms.",
     "parameters": {"type": "OBJECT",
                    "properties": {"filename": {"type": "STRING"},
                                   "content": {"type": "STRING"},
                                   "overwrite": {"type": "BOOLEAN"}},
                    "required": ["filename", "content"]}},
    {"name": "append_file",
     "description": "Append text to a plain-text file (created if missing).",
     "parameters": {"type": "OBJECT",
                    "properties": {"filename": {"type": "STRING"},
                                   "content": {"type": "STRING"}},
                    "required": ["filename", "content"]}},
]

# --- Audio ---
INPUT_RATE = 16000    # Gemini Live wil 16 kHz in
OUTPUT_RATE = 24000   # en stuurt 24 kHz terug
try:
    DEVICE_RATE = int(sd.query_devices(kind="output")["default_samplerate"])
except Exception:
    DEVICE_RATE = 48000
BLOCK_IN = INPUT_RATE // 50  # 20 ms


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    if src == dst or len(x) == 0:
        return x
    if src % dst == 0:
        k = src // dst
        n = len(x) // k * k
        return x[:n].reshape(-1, k).mean(axis=1).astype(np.float32)
    n = int(len(x) * dst / src)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


class Speaker:
    """Doorlopende outputstream met fades, zelfde idee als Jarvis.py."""

    FADE = 0.008

    def __init__(self, rate: int):
        self.rate = rate
        self.lock = threading.Lock()
        self.buf = np.zeros(0, dtype=np.float32)
        self.gen = 0
        self.stream = sd.OutputStream(samplerate=rate, channels=1,
                                      dtype="float32", callback=self._callback)
        self.stream.start()

    def _callback(self, outdata, frames, time_info, status):
        with self.lock:
            n = min(frames, len(self.buf))
            outdata[:n, 0] = self.buf[:n]
            outdata[n:, 0] = 0.0
            self.buf = self.buf[n:]

    def interrupt(self):
        with self.lock:
            self.gen += 1
            n = min(int(self.rate * 0.02), len(self.buf))
            if n:
                self.buf = (self.buf[:n] * np.linspace(1.0, 0.0, n, dtype=np.float32)).copy()
            else:
                self.buf = self.buf[:0]

    def add_pcm16(self, pcm: bytes, gen: int, src_rate: int):
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        audio = resample(audio, src_rate, self.rate)
        n = min(int(self.rate * self.FADE), len(audio) // 2)
        if n > 0:
            ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
            audio[:n] *= ramp
            audio[-n:] *= ramp[::-1]
        with self.lock:
            if gen == self.gen:
                self.buf = np.concatenate([self.buf, audio])


async def run_session():
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("Pakket 'google-genai' ontbreekt. Installeer met:")
        print("  .venv/Scripts/python.exe -m pip install google-genai python-dotenv")
        sys.exit(1)

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("GEMINI_API_KEY ontbreekt. Zet hem in .env (zie .env.example).")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=SYSTEM_PROMPT,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICE)
            )
        ),
        tools=[types.Tool(function_declarations=FUNCTION_DECLARATIONS)],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    mic_q: queue.Queue = queue.Queue(maxsize=200)

    def mic_cb(indata, frames, time_info, status):
        try:
            mic_q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass  # oudste droppen is beter dan geheugen laten groeien

    mic = sd.InputStream(samplerate=INPUT_RATE, channels=1,
                         dtype="float32", blocksize=BLOCK_IN, callback=mic_cb)
    speaker = Speaker(DEVICE_RATE)
    gen = speaker.gen
    stop = asyncio.Event()

    print(f"Verbinden met {GEMINI_MODEL} (stem {GEMINI_VOICE}) ...")
    try:
        async with client.aio.live.connect(model=GEMINI_MODEL, config=config) as session:
            print("Verbonden. Praat gewoon, zeg 'goodbye' om te stoppen. Ctrl+C werkt ook.")

            async def sender():
                loop = asyncio.get_running_loop()
                while not stop.is_set():
                    block = await loop.run_in_executor(None, mic_q.get)
                    pcm16 = (np.clip(block, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                    try:
                        await session.send_realtime_input(
                            audio=types.Blob(data=pcm16, mime_type="audio/pcm;rate=16000"))
                    except Exception as e:
                        print(f"[zend-fout] {e}")
                        break

            async def receiver():
                nonlocal gen
                try:
                    async for msg in session.receive():
                        # 1. tool calls
                        tool_calls = getattr(msg, "tool_call", None)
                        calls = getattr(tool_calls, "function_calls", None) if tool_calls else None
                        if calls:
                            responses = []
                            for call in calls:
                                name = getattr(call, "name", "")
                                args = getattr(call, "args", {}) or {}
                                call_id = getattr(call, "id", None)
                                print(f"[bestand] {name}({args})")
                                try:
                                    fn = TOOLS.get(name)
                                    result = fn(**args) if fn else f"Unknown tool: {name}"
                                except Exception as e:
                                    result = f"Error: {e}"
                                print(f"[bestand] -> {str(result)[:100]!r}")
                                fr = {"name": name, "response": {"result": str(result)}}
                                if call_id:
                                    fr["id"] = call_id
                                responses.append(fr)
                            try:
                                from google.genai import types as t
                                await session.send_tool_response(
                                    function_responses=[t.FunctionResponse(**r) for r in responses])
                            except Exception as e:
                                print(f"[tool-fout] {e}")
                            continue

                        server = getattr(msg, "server_content", None)
                        if server is None:
                            continue

                        if getattr(server, "interrupted", False):
                            speaker.interrupt()
                            gen = speaker.gen
                            print("[status] onderbroken")
                            continue

                        # transcripten voor in de terminal
                        in_t = getattr(server, "input_transcription", None)
                        if in_t and getattr(in_t, "text", ""):
                            print(f"Jij: {in_t.text}")
                            if "goodbye" in in_t.text.lower():
                                stop.set()
                                return
                        out_t = getattr(server, "output_transcription", None)
                        if out_t and getattr(out_t, "text", ""):
                            print(f"J.A.R.V.I.S.: {out_t.text}", end=" ", flush=True)

                        turn = getattr(server, "model_turn", None)
                        parts = getattr(turn, "parts", []) if turn else []
                        for part in parts:
                            blob = getattr(part, "inline_data", None)
                            if blob and getattr(blob, "data", None):
                                speaker.add_pcm16(blob.data, gen, OUTPUT_RATE)
                except Exception as e:
                    print(f"\n[ontvang-fout] {e}")
                    stop.set()

            mic.start()
            try:
                await asyncio.gather(sender(), receiver())
            finally:
                mic.stop()
    finally:
        speaker.stream.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run_session())
    except KeyboardInterrupt:
        print("\nGestopt, Sir.")
