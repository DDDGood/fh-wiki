"""Tkinter GUI for the telemetry recorder.

Single-window app that hosts the Recorder in a background thread. Three tabs:
    狀態     - live recorder state, packet rate, current session
    賽事資料 - sessions/ list with summary preview, regen, delete
    車輛資料 - cars/*.yml list with new/edit/delete (uses OS default editor)

Bottom bar (always visible):
    啟動/停止 recorder | 強制錄製 / 強制停止 | 大字狀態指示

Run: python -m scripts.forza_telemetry.gui
or double-click start-telemetry-gui.bat
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog, ttk

from .recorder import Recorder, RecorderConfig

log = logging.getLogger("forza_telemetry")

# Color palettes — VS Code Dark+ inspired so summary headers/code blocks look
# familiar. Recorder-state colors live inside the palette (state_idle / state_*).
DARK = {
    "bg":          "#1e1e1e",
    "bg_alt":      "#252526",
    "bg_widget":   "#2d2d30",
    "fg":          "#d4d4d4",
    "fg_dim":      "#888888",
    "accent":      "#0e639c",
    "accent_fg":   "#ffffff",
    "select_bg":   "#264f78",
    "border":      "#3c3c3c",
    "value_fg":    "#9cdcfe",
    "h1":          "#4ec9b0",
    "h2":          "#9cdcfe",
    "h3":          "#ce9178",
    "bold":        "#dcdcaa",
    "code_fg":     "#ce9178",
    "code_bg":     "#2d2d30",
    "hr":          "#3c3c3c",
    "state_idle":      "#888888",
    "state_buffering": "#dcdcaa",
    "state_recording": "#f48771",
    "state_stopped":   "#666666",
}

LIGHT = {
    "bg":          "#f0f0f0",
    "bg_alt":      "#ffffff",
    "bg_widget":   "#ffffff",
    "fg":          "#1a1a1a",
    "fg_dim":      "#666666",
    "accent":      "#0066cc",
    "accent_fg":   "#ffffff",
    "select_bg":   "#cce4ff",
    "border":      "#cccccc",
    "value_fg":    "#0a3a7a",
    "h1":          "#005a9e",
    "h2":          "#0066cc",
    "h3":          "#a0522d",
    "bold":        "#7a5c00",
    "code_fg":     "#a31515",
    "code_bg":     "#f4f4f4",
    "hr":          "#cccccc",
    "state_idle":      "#666666",
    "state_buffering": "#cc8800",
    "state_recording": "#cc0033",
    "state_stopped":   "#888888",
}


class App:
    POLL_MS = 500
    SUMMARY_FONT_DEFAULT = 10
    SUMMARY_FONT_MIN = 7
    SUMMARY_FONT_MAX = 22

    def __init__(self, root: tk.Tk, config: RecorderConfig, palette: dict | None = None) -> None:
        self.root = root
        self.config = config
        self.sessions_dir = config.output_dir
        self.cars_dir = config.output_dir.parent / "cars"
        self.palette = palette if palette is not None else DARK
        self._summary_font_size = self.SUMMARY_FONT_DEFAULT

        self.recorder: Recorder | None = None
        self.recorder_thread: threading.Thread | None = None

        self._apply_theme()
        self._build_ui()
        self._refresh_sessions()
        self._refresh_cars()
        self._poll()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ──────────────────────────── theming ────────────────────────────

    def _apply_theme(self) -> None:
        P = self.palette
        style = ttk.Style()
        # 'clam' is the most styleable built-in theme — required for our palette
        # to take effect on Windows (default 'vista' theme ignores most colors).
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.root.config(bg=P["bg"])

        style.configure(".", background=P["bg"], foreground=P["fg"], fieldbackground=P["bg_alt"])
        style.configure("TFrame", background=P["bg"])
        style.configure("TLabel", background=P["bg"], foreground=P["fg"])
        style.configure(
            "TButton",
            background=P["bg_widget"],
            foreground=P["fg"],
            bordercolor=P["border"],
            lightcolor=P["bg_widget"],
            darkcolor=P["bg_widget"],
            focuscolor=P["accent"],
            padding=(8, 4),
        )
        style.map(
            "TButton",
            background=[("active", P["accent"]), ("disabled", P["bg"])],
            foreground=[("disabled", P["fg_dim"]), ("active", P["accent_fg"])],
        )
        style.configure("TNotebook", background=P["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=P["bg_alt"],
            foreground=P["fg"],
            padding=(14, 6),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", P["accent"])],
            foreground=[("selected", P["accent_fg"])],
        )
        style.configure(
            "Treeview",
            background=P["bg_alt"],
            foreground=P["fg"],
            fieldbackground=P["bg_alt"],
            borderwidth=0,
            rowheight=22,
        )
        style.configure(
            "Treeview.Heading",
            background=P["bg_widget"],
            foreground=P["fg"],
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", P["select_bg"])],
            foreground=[("selected", P["fg"])],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", P["accent"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=P["bg_widget"],
            troughcolor=P["bg"],
            bordercolor=P["bg"],
            arrowcolor=P["fg"],
            borderwidth=0,
        )
        style.configure(
            "Horizontal.TScrollbar",
            background=P["bg_widget"],
            troughcolor=P["bg"],
            bordercolor=P["bg"],
            arrowcolor=P["fg"],
            borderwidth=0,
        )
        style.configure("TPanedwindow", background=P["bg"])
        style.configure("TSeparator", background=P["border"])

        # Custom styles for status values (brighter color than label text)
        style.configure("Value.TLabel", background=P["bg"], foreground=P["value_fg"], font=("Consolas", 10))
        style.configure("Hint.TLabel", background=P["bg"], foreground=P["fg_dim"], font=("Consolas", 9))

    # ──────────────────────────── UI build ────────────────────────────

    def _build_ui(self) -> None:
        self.root.title("Forza Telemetry")
        self.root.geometry("1100x720")

        self._build_bottom_bar()

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True)
        self._build_status_tab()
        self._build_sessions_tab()
        self._build_cars_tab()

    def _build_bottom_bar(self) -> None:
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.btn_recorder = ttk.Button(
            bar, text="▶ 啟動 recorder", width=18, command=self._toggle_recorder
        )
        self.btn_recorder.pack(side=tk.LEFT, padx=4)

        self.btn_force_record = ttk.Button(
            bar, text="● 強制錄製", width=12, command=self._force_record, state=tk.DISABLED
        )
        self.btn_force_record.pack(side=tk.LEFT, padx=4)

        self.btn_force_stop = ttk.Button(
            bar, text="■ 強制停止", width=12, command=self._force_stop, state=tk.DISABLED
        )
        self.btn_force_stop.pack(side=tk.LEFT, padx=4)

        P = self.palette
        ttk.Label(bar, text=f"port {self.config.port}", style="Hint.TLabel").pack(side=tk.LEFT, padx=12)

        self.lbl_state_big = tk.Label(
            bar,
            text="STOPPED",
            font=("Segoe UI", 13, "bold"),
            fg=P["state_stopped"],
            bg=P["bg"],
        )
        self.lbl_state_big.pack(side=tk.RIGHT, padx=10)

    def _build_status_tab(self) -> None:
        f = ttk.Frame(self.nb, padding=16)
        self.nb.add(f, text="狀態")

        self._status_vars: dict[str, tk.StringVar] = {}
        rows = [
            ("Recorder", "recorder_state"),
            ("封包速率", "packet_rate"),
            ("最後封包", "last_packet"),
            ("IsRaceOn", "is_race_on"),
            ("車輛 ordinal", "car_ordinal"),
            ("PI", "car_pi"),
            ("即時車速", "speed"),
            ("Buffered packets", "buffer_size"),
            ("當前 session", "session_folder"),
            ("Session packet 數", "session_packet_count"),
            ("Idle 計時", "idle_seconds"),
        ]
        for i, (label, key) in enumerate(rows):
            ttk.Label(f, text=label, width=20, anchor="w").grid(row=i, column=0, sticky="w", pady=3)
            v = tk.StringVar(value="—")
            self._status_vars[key] = v
            ttk.Label(f, textvariable=v, style="Value.TLabel").grid(row=i, column=1, sticky="w", pady=3)

        # FH5 setup hint
        hint = (
            "FH5 → HUD → Data Out:\n"
            f"  Data Out IP    : 127.0.0.1\n"
            f"  Data Out Port  : {self.config.port}\n"
            f"  Packet Format  : Car Dash (不要選 Sled)"
        )
        ttk.Label(f, text=hint, style="Hint.TLabel", justify=tk.LEFT).grid(
            row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(20, 0)
        )

    def _build_sessions_tab(self) -> None:
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="賽事資料")

        paned = ttk.PanedWindow(f, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Left: list (grid layout — tree+scrollbar in row 0, button bar spans row 1)
        left = ttk.Frame(paned)
        paned.add(left, weight=1)
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        cols = ("started", "car", "pi", "duration", "laps", "best")
        self.tv_sessions = ttk.Treeview(left, columns=cols, show="headings", height=22)
        for c, label, w in zip(
            cols,
            ["開始", "車", "PI", "時長", "圈", "最佳"],
            [140, 180, 50, 70, 40, 80],
        ):
            self.tv_sessions.heading(c, text=label)
            self.tv_sessions.column(c, width=w, anchor=tk.W)
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tv_sessions.yview)
        self.tv_sessions.config(yscrollcommand=sb.set)
        self.tv_sessions.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tv_sessions.bind("<<TreeviewSelect>>", self._on_session_select)

        bf = ttk.Frame(left)
        bf.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(bf, text="🔄 重整", command=self._refresh_sessions).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="📂 開資料夾", command=self._open_session_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="🔁 重生 summary", command=self._regen_summary).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="🗑 刪除", command=self._delete_session).pack(side=tk.RIGHT, padx=2)

        # Right: summary preview (Markdown-rendered via tk.Text tags)
        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        # Toolbar above the text — font controls + hint
        tb = ttk.Frame(right)
        tb.pack(fill=tk.X, padx=4, pady=(0, 2))
        ttk.Label(tb, text="字體", style="Hint.TLabel").pack(side=tk.LEFT, padx=(2, 4))
        ttk.Button(tb, text="−", width=3, command=lambda: self._summary_zoom(-1)).pack(side=tk.LEFT, padx=1)
        ttk.Button(tb, text="+", width=3, command=lambda: self._summary_zoom(+1)).pack(side=tk.LEFT, padx=1)
        ttk.Button(tb, text="重置", width=5, command=self._summary_zoom_reset).pack(side=tk.LEFT, padx=1)
        ttk.Label(tb, text="（Ctrl+滾輪也可調）", style="Hint.TLabel").pack(side=tk.LEFT, padx=8)

        P = self.palette
        self.txt_summary = scrolledtext.ScrolledText(
            right,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=P["bg_alt"],
            fg=P["fg"],
            insertbackground=P["fg"],
            selectbackground=P["select_bg"],
            selectforeground=P["fg"],
            relief=tk.FLAT,
            borderwidth=0,
            padx=12,
            pady=8,
        )
        self.txt_summary.pack(fill=tk.BOTH, expand=True)
        self._configure_summary_tags()
        # Ctrl+wheel / Ctrl+= / Ctrl+- / Ctrl+0
        self.txt_summary.bind(
            "<Control-MouseWheel>",
            lambda e: self._summary_zoom(1 if e.delta > 0 else -1),
        )
        for key in ("equal", "plus", "KP_Add"):
            self.txt_summary.bind(f"<Control-{key}>", lambda _e: self._summary_zoom(+1))
        for key in ("minus", "KP_Subtract"):
            self.txt_summary.bind(f"<Control-{key}>", lambda _e: self._summary_zoom(-1))
        self.txt_summary.bind("<Control-Key-0>", lambda _e: self._summary_zoom_reset())

    def _build_cars_tab(self) -> None:
        f = ttk.Frame(self.nb, padding=6)
        self.nb.add(f, text="車輛資料")

        cols = ("ordinal", "name", "purpose", "class", "modified")
        self.tv_cars = ttk.Treeview(f, columns=cols, show="headings", height=22)
        for c, label, w in zip(
            cols,
            ["Ordinal", "車名", "用途", "Class", "最後修改"],
            [80, 280, 90, 80, 140],
        ):
            self.tv_cars.heading(c, text=label)
            self.tv_cars.column(c, width=w, anchor=tk.W)
        self.tv_cars.bind("<Double-1>", lambda _e: self._edit_car())
        self.tv_cars.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        bf = ttk.Frame(f)
        bf.pack(fill=tk.X)
        ttk.Button(bf, text="🔄 重整", command=self._refresh_cars).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="➕ 新增", command=self._new_car).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="✏️ 編輯（系統預設編輯器）", command=self._edit_car).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="📂 開 cars/ 資料夾", command=self._open_cars_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="🗑 刪除", command=self._delete_car).pack(side=tk.RIGHT, padx=2)

    # ──────────────────────────── summary rendering ────────────────────────────

    def _configure_summary_tags(self) -> None:
        """(Re)apply tk.Text tag styles for markdown rendering. Re-run after font zoom."""
        s = self._summary_font_size
        P = self.palette
        txt = self.txt_summary
        body_font = ("Consolas", s)
        ui_font = ("Segoe UI", s)
        # Base widget font (un-tagged text)
        txt.config(font=ui_font)

        txt.tag_configure("h1", font=("Segoe UI", s + 7, "bold"), foreground=P["h1"], spacing1=14, spacing3=6)
        txt.tag_configure("h2", font=("Segoe UI", s + 4, "bold"), foreground=P["h2"], spacing1=10, spacing3=4)
        txt.tag_configure("h3", font=("Segoe UI", s + 2, "bold"), foreground=P["h3"], spacing1=8, spacing3=3)
        txt.tag_configure("bold", font=("Segoe UI", s, "bold"), foreground=P["bold"])
        txt.tag_configure("code", font=body_font, foreground=P["code_fg"], background=P["code_bg"])
        txt.tag_configure(
            "codeblock",
            font=body_font,
            foreground=P["fg"],
            background=P["code_bg"],
            lmargin1=20,
            lmargin2=20,
            spacing1=2,
            spacing3=2,
        )
        txt.tag_configure("table", font=body_font, foreground=P["fg"])
        txt.tag_configure("hr", foreground=P["hr"], spacing1=4, spacing3=4)
        txt.tag_configure("bullet", lmargin1=12, lmargin2=24)

    def _render_markdown(self, content: str) -> None:
        """Render markdown into the summary widget using tag-based formatting.

        Supports: # ## ### headers, **bold**, `code`, ``` blocks ```, | tables |, --- hr,
        and list bullets (- / *). Limitations: no inline links/images, tables stay
        as raw monospace text (column alignment preserved by font choice).
        """
        txt = self.txt_summary
        txt.config(state=tk.NORMAL)
        txt.delete("1.0", tk.END)

        in_code_block = False
        for raw in content.split("\n"):
            stripped = raw.lstrip()

            # Code fence toggles state but produces no visible output.
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                txt.insert(tk.END, raw + "\n", "codeblock")
                continue

            # Headers
            if stripped.startswith("### "):
                txt.insert(tk.END, stripped[4:] + "\n", "h3")
                continue
            if stripped.startswith("## "):
                txt.insert(tk.END, stripped[3:] + "\n", "h2")
                continue
            if stripped.startswith("# "):
                txt.insert(tk.END, stripped[2:] + "\n", "h1")
                continue

            # Horizontal rule
            if stripped in ("---", "***", "___"):
                txt.insert(tk.END, "─" * 60 + "\n", "hr")
                continue

            # Tables: any line starting with '|' kept as-is, monospace font
            if stripped.startswith("|"):
                txt.insert(tk.END, raw + "\n", "table")
                continue

            # Bullet list: convert "- foo" / "* foo" to "• foo" with indent
            if stripped.startswith(("- ", "* ")):
                indent = len(raw) - len(stripped)
                txt.insert(tk.END, " " * indent + "• ", "bullet")
                self._insert_inline(stripped[2:] + "\n")
                continue

            # Plain line with inline **bold** and `code`
            self._insert_inline(raw + "\n")

        txt.config(state=tk.DISABLED)

    _INLINE_RE = re.compile(r"(\*\*[^\*\n]+\*\*|`[^`\n]+`)")

    def _insert_inline(self, line: str) -> None:
        """Insert a line into txt_summary, applying 'bold' and 'code' tags inline."""
        txt = self.txt_summary
        pos = 0
        for m in self._INLINE_RE.finditer(line):
            if m.start() > pos:
                txt.insert(tk.END, line[pos : m.start()])
            token = m.group(0)
            if token.startswith("**"):
                txt.insert(tk.END, token[2:-2], "bold")
            else:  # `code`
                txt.insert(tk.END, token[1:-1], "code")
            pos = m.end()
        if pos < len(line):
            txt.insert(tk.END, line[pos:])

    def _summary_zoom(self, delta: int) -> None:
        new_size = max(self.SUMMARY_FONT_MIN, min(self.SUMMARY_FONT_MAX, self._summary_font_size + delta))
        if new_size == self._summary_font_size:
            return
        self._summary_font_size = new_size
        self._configure_summary_tags()
        # Re-render currently displayed summary so font/tag changes apply.
        sess = self._selected_session()
        if sess and (sess / "summary.md").is_file():
            self._render_markdown((sess / "summary.md").read_text(encoding="utf-8"))

    def _summary_zoom_reset(self) -> None:
        if self._summary_font_size == self.SUMMARY_FONT_DEFAULT:
            return
        self._summary_font_size = self.SUMMARY_FONT_DEFAULT
        self._configure_summary_tags()
        sess = self._selected_session()
        if sess and (sess / "summary.md").is_file():
            self._render_markdown((sess / "summary.md").read_text(encoding="utf-8"))

    # ──────────────────────────── recorder lifecycle ────────────────────────────

    def _toggle_recorder(self) -> None:
        if self.recorder is None:
            self._start_recorder()
        else:
            self._stop_recorder()

    def _start_recorder(self) -> None:
        try:
            self.recorder = Recorder(config=self.config)
            self.recorder_thread = threading.Thread(
                target=self.recorder.run, daemon=True, name="recorder"
            )
            self.recorder_thread.start()
        except Exception as e:
            log.exception("failed to start recorder")
            messagebox.showerror("錯誤", f"啟動 recorder 失敗：\n{e}")
            self.recorder = None
            self.recorder_thread = None
            return
        self.btn_recorder.config(text="⏹ 停止 recorder")
        self.btn_force_record.config(state=tk.NORMAL)
        self.btn_force_stop.config(state=tk.NORMAL)

    def _stop_recorder(self) -> None:
        if self.recorder is None:
            return
        self.recorder.stop()
        if self.recorder_thread is not None:
            self.recorder_thread.join(timeout=5)
        self.recorder = None
        self.recorder_thread = None
        self.btn_recorder.config(text="▶ 啟動 recorder")
        self.btn_force_record.config(state=tk.DISABLED)
        self.btn_force_stop.config(state=tk.DISABLED)
        # Refresh sessions list since a finalize may have just happened.
        self._refresh_sessions()

    def _force_record(self) -> None:
        if self.recorder:
            self.recorder.force_record()

    def _force_stop(self) -> None:
        if self.recorder:
            self.recorder.force_stop()
            # New session may have just been finalized → refresh listing.
            self.root.after(500, self._refresh_sessions)

    # ──────────────────────────── status polling ────────────────────────────

    def _poll(self) -> None:
        try:
            self._update_status()
        except Exception:
            log.exception("status poll failed")
        self.root.after(self.POLL_MS, self._poll)

    def _update_status(self) -> None:
        P = self.palette
        if self.recorder is None:
            self.lbl_state_big.config(text="STOPPED", fg=P["state_stopped"])
            for v in self._status_vars.values():
                v.set("—")
            self._status_vars["recorder_state"].set("STOPPED")
            return

        snap = self.recorder.snapshot()
        state = snap["state"]
        self.lbl_state_big.config(text=state.upper(), fg=P[f"state_{state}"])
        self._status_vars["recorder_state"].set(state.upper())
        self._status_vars["packet_rate"].set(f'{snap["packet_rate_hz"]:.0f} Hz')
        if snap["last_packet_at"]:
            ago = time.monotonic() - snap["last_packet_at"]
            self._status_vars["last_packet"].set(f"{ago:.1f}s 前")
        else:
            self._status_vars["last_packet"].set("（無）")
        self._status_vars["is_race_on"].set(
            "—" if snap["is_race_on"] is None else str(snap["is_race_on"])
        )
        self._status_vars["car_ordinal"].set(
            "—" if not snap["car_ordinal"] else str(snap["car_ordinal"])
        )
        self._status_vars["car_pi"].set("—" if not snap["car_pi"] else str(snap["car_pi"]))
        self._status_vars["speed"].set(
            "—" if snap["speed_kmh"] is None else f'{snap["speed_kmh"]:.0f} km/h'
        )
        self._status_vars["buffer_size"].set(str(snap["buffer_size"]))
        sess_folder = snap["session_folder"]
        self._status_vars["session_folder"].set(
            Path(sess_folder).name if sess_folder else "—"
        )
        self._status_vars["session_packet_count"].set(str(snap["session_packet_count"]))
        idle = snap["idle_seconds"]
        self._status_vars["idle_seconds"].set(f"{idle:.1f}s" if idle > 0 else "—")

    # ──────────────────────────── sessions tab ────────────────────────────

    def _refresh_sessions(self) -> None:
        self.tv_sessions.delete(*self.tv_sessions.get_children())
        if not self.sessions_dir.is_dir():
            return
        for d in sorted(
            (x for x in self.sessions_dir.iterdir() if x.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        ):
            meta_p = d / "meta.json"
            if not meta_p.is_file():
                # Show even un-finalized sessions but with placeholders.
                self.tv_sessions.insert("", tk.END, iid=d.name, values=(d.name[:16], "（未完成）", "", "", "", ""))
                continue
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
            except Exception:
                continue
            car = meta.get("car", {})
            db = car.get("db") or {}
            car_label = db.get("name") or f"ordinal {car.get('ordinal', '?')}"
            pi = car.get("performance_index", "")
            duration = meta.get("duration_seconds", 0)
            race = meta.get("race", {})
            laps = race.get("total_laps", 0)
            best = race.get("best_lap_seconds")
            best_str = f"{best:.3f}" if best else "—"
            started = (meta.get("started_at") or "")[:16].replace("T", " ")
            self.tv_sessions.insert(
                "",
                tk.END,
                iid=d.name,
                values=(started, car_label, pi, f"{duration:.0f}s", laps, best_str),
            )

    def _selected_session(self) -> Path | None:
        sel = self.tv_sessions.selection()
        if not sel:
            return None
        return self.sessions_dir / sel[0]

    def _on_session_select(self, _event=None) -> None:
        sess = self._selected_session()
        if sess is None:
            self._render_markdown("")
            return
        summary = sess / "summary.md"
        if summary.is_file():
            self._render_markdown(summary.read_text(encoding="utf-8"))
        else:
            self._render_markdown("_（這場 session 還沒有 summary.md，按「重生 summary」可以產生）_")

    def _open_session_folder(self) -> None:
        sess = self._selected_session()
        if sess is None:
            messagebox.showinfo("提示", "請先選一筆 session")
            return
        _open_in_explorer(sess)

    def _regen_summary(self) -> None:
        sess = self._selected_session()
        if sess is None:
            messagebox.showinfo("提示", "請先選一筆 session")
            return
        try:
            from .summarize import build_report

            summary, corners = build_report(sess)
            (sess / "summary.md").write_text(summary, encoding="utf-8")
            if corners:
                (sess / "corners_detail.md").write_text(corners, encoding="utf-8")
            self._on_session_select()
            messagebox.showinfo("OK", "summary.md 已重新生成")
        except Exception as e:
            log.exception("regen summary failed")
            messagebox.showerror("錯誤", f"重生 summary 失敗：\n{e}")

    def _delete_session(self) -> None:
        sess = self._selected_session()
        if sess is None:
            messagebox.showinfo("提示", "請先選一筆 session")
            return
        if not messagebox.askyesno(
            "確認刪除",
            f"刪除 session {sess.name} ？\n\n資料夾與內容會全部移除（無法復原）。",
        ):
            return
        try:
            shutil.rmtree(sess)
        except Exception as e:
            messagebox.showerror("錯誤", f"刪除失敗：\n{e}")
            return
        self._refresh_sessions()
        self.txt_summary.config(state=tk.NORMAL)
        self.txt_summary.delete("1.0", tk.END)
        self.txt_summary.config(state=tk.DISABLED)

    # ──────────────────────────── cars tab ────────────────────────────

    def _refresh_cars(self) -> None:
        self.tv_cars.delete(*self.tv_cars.get_children())
        if not self.cars_dir.is_dir():
            return
        try:
            import yaml
        except ImportError:
            self.tv_cars.insert("", tk.END, values=("?", "需要 pyyaml: pip install pyyaml", "", "", ""))
            return
        for fp in sorted(self.cars_dir.glob("*.yml")):
            if fp.name.startswith("_"):
                continue
            try:
                data = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
            except Exception as e:
                self.tv_cars.insert(
                    "", tk.END, iid=fp.name, values=(fp.stem, f"(無法解析：{e})", "", "", "")
                )
                continue
            ordinal = data.get("ordinal", fp.stem)
            modified = datetime.fromtimestamp(fp.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            self.tv_cars.insert(
                "",
                tk.END,
                iid=fp.name,
                values=(
                    ordinal,
                    data.get("name", ""),
                    data.get("purpose", ""),
                    data.get("class", ""),
                    modified,
                ),
            )

    def _selected_car(self) -> Path | None:
        sel = self.tv_cars.selection()
        if not sel:
            return None
        return self.cars_dir / sel[0]

    def _new_car(self) -> None:
        ordinal = simpledialog.askstring(
            "新增車輛", "請輸入 CarOrdinal（純數字，從 session 資料夾名稱可看到）：", parent=self.root
        )
        if not ordinal:
            return
        ordinal = ordinal.strip()
        if not ordinal.isdigit():
            messagebox.showerror("錯誤", "ordinal 必須是純數字")
            return
        target = self.cars_dir / f"{ordinal}.yml"
        if target.exists():
            messagebox.showerror("錯誤", f"{target.name} 已存在")
            return
        template = self.cars_dir / "_template.yml"
        if not template.is_file():
            messagebox.showerror("錯誤", f"找不到範本檔：\n{template}")
            return
        self.cars_dir.mkdir(parents=True, exist_ok=True)
        content = template.read_text(encoding="utf-8").replace("ordinal: 0000", f"ordinal: {ordinal}")
        target.write_text(content, encoding="utf-8")
        self._refresh_cars()
        _open_in_default_editor(target)

    def _edit_car(self) -> None:
        car = self._selected_car()
        if car is None:
            messagebox.showinfo("提示", "請先選一台車")
            return
        _open_in_default_editor(car)

    def _open_cars_folder(self) -> None:
        self.cars_dir.mkdir(parents=True, exist_ok=True)
        _open_in_explorer(self.cars_dir)

    def _delete_car(self) -> None:
        car = self._selected_car()
        if car is None:
            messagebox.showinfo("提示", "請先選一台車")
            return
        if not messagebox.askyesno("確認刪除", f"刪除 {car.name}？"):
            return
        try:
            car.unlink()
        except Exception as e:
            messagebox.showerror("錯誤", f"刪除失敗：\n{e}")
            return
        self._refresh_cars()

    # ──────────────────────────── close ────────────────────────────

    def _on_close(self) -> None:
        if self.recorder is not None:
            self._stop_recorder()
        self.root.destroy()


def _open_in_explorer(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        import subprocess
        subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", str(path)])


def _open_in_default_editor(path: Path) -> None:
    # Same as explorer on Windows — startfile uses the registered handler.
    _open_in_explorer(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.forza_telemetry.gui",
        description="Tkinter GUI for the Forza telemetry recorder.",
    )
    parser.add_argument("--port", type=int, default=5300)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/forza_telemetry/sessions")
    )
    parser.add_argument(
        "--auto-start", action="store_true", help="開窗後自動啟動 recorder（不用手動按按鈕）"
    )
    parser.add_argument(
        "--theme", choices=["dark", "light"], default="dark", help="配色（預設：dark）"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    config = RecorderConfig(
        port=args.port, bind_host=args.bind, output_dir=args.output_dir
    )

    palette = DARK if args.theme == "dark" else LIGHT
    root = tk.Tk()
    app = App(root, config, palette=palette)
    if args.auto_start:
        app._start_recorder()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
