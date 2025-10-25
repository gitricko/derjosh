#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GUI launcher for approx_borrow_size_analysis.py
- Select options by clicking
- Launch Overview, Detail, or Both
"""

import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os, json
APP_NAME = "ApproxBorrowSize"
APPDATA = os.getenv("APPDATA")
CONFIG_HOME = os.path.expanduser("~/.config")
PRESET_DIR = os.path.join(APPDATA if APPDATA else CONFIG_HOME, APP_NAME)
SETTINGS_FILE = os.path.join(PRESET_DIR, "presets.json")
import os, json
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "user_presets.json")

DEFAULT_SCRIPT = "approx_borrow_size_analysis.py"

class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Approx Borrow Size – Launcher (BZAP)")
        try:
            os.makedirs(PRESET_DIR, exist_ok=True)
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.geometry("820x850")
        self.minsize(780, 580)

        # --- Vars ---
        self.script = tk.StringVar(value=DEFAULT_SCRIPT)
        self.data_dir = tk.StringVar(value="./data")
        self.days = tk.IntVar(value=5)
        self.topN = tk.IntVar(value=9)
        self.overview_rank = tk.StringVar(value="dev_cum")
        self.detail_order = tk.StringVar(value="overview")
        self.date_mode = tk.StringVar(value="data")        
        self.detail = tk.BooleanVar(value=True)
        self.x_mode = tk.StringVar(value="time")
        self.borrow_view = tk.StringVar(value="absolute")
        self.delta_baseline = tk.StringVar(value="first")
        self.borrow_zoom_frac = tk.DoubleVar(value=0.0)
        self.borrow_zoom_on = tk.BooleanVar(value=False)
        self.borrow_floor_mode = tk.StringVar(value="none")
        self.initial_symbol = tk.StringVar(value="")
        self.debug = tk.BooleanVar(value=False)

        self.sep = tk.StringVar(value="")        # optional
        self.symbol_col = tk.StringVar(value="") # optional
        self.price_col = tk.StringVar(value="")  # optional
        self.borrow_col = tk.StringVar(value="") # optional

        # Load presets at startup
        self._load_presets()


        self._build_ui()
        self._update_cmd_preview()

    # ---------- UI ----------
    def _build_ui(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        # Script + Data dir
        box_top = ttk.LabelFrame(frm, text="Target Script & Data", padding=10)
        box_top.pack(fill="x")

        row = ttk.Frame(box_top)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Target script:").pack(side="left")
        e_script = ttk.Entry(row, textvariable=self.script, width=40)
        e_script.pack(side="left", padx=5)
        ttk.Button(row, text="Browse file…", command=self._pick_script).pack(side="left")

        row = ttk.Frame(box_top)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Data folder:").pack(side="left")
        e_dir = ttk.Entry(row, textvariable=self.data_dir, width=40)
        e_dir.pack(side="left", padx=5)
        ttk.Button(row, text="Browse folder…", command=self._pick_dir).pack(side="left")

        # Options
        box_opts = ttk.LabelFrame(frm, text="Options", padding=10)
        box_opts.pack(fill="x", pady=8)

        # left column
        colL = ttk.Frame(box_opts)
        colL.pack(side="left", fill="y", padx=(0,10))

        ttk.Label(colL, text="Days (excluding weekends):").pack(anchor="w")
        ttk.Spinbox(colL, from_=1, to=30, textvariable=self.days, width=6).pack(anchor="w")

        ttk.Label(colL, text="Top N in Overview:").pack(anchor="w", pady=(8,0))
        ttk.Spinbox(colL, from_=1, to=30, textvariable=self.topN, width=6).pack(anchor="w")

        ttk.Label(colL, text="Datemode:").pack(anchor="w", pady=(8,0))
        for v, txt2 in [("data","All Days"), ("weekday","Without Weekend")]:
            ttk.Radiobutton(colL, text=txt2, value=v, variable=self.date_mode, command=self._update_cmd_preview).pack(anchor="w")

        ttk.Label(colL, text="Overview ranking:").pack(anchor="w", pady=(8,0))
        for v, txt in [("dev_cum","Deviation BZAP(cum)"), ("borrow","ΣBorrow"), ("alpha","Alphabetical")]:
            ttk.Radiobutton(colL, text=txt, value=v, variable=self.overview_rank, command=self._update_cmd_preview).pack(anchor="w")

        ttk.Label(colL, text="Detail order:").pack(anchor="w", pady=(8,0))
        for v, txt in [("overview","same as Overview"), ("dev_cum","Deviation BZAP(cum)"), ("borrow","ΣBorrow"), ("alpha","Alphabetical")]:
            ttk.Radiobutton(colL, text=txt, value=v, variable=self.detail_order, command=self._update_cmd_preview).pack(anchor="w")

        # middle column
        colM = ttk.Frame(box_opts)
        colM.pack(side="left", fill="y", padx=(0,10))

        ttk.Label(colM, text="X axis:").pack(anchor="w")
        for v, txt in [("time","Timestamp"), ("index","Equally spaced")]:
            ttk.Radiobutton(colM, text=txt, value=v, variable=self.x_mode, command=self._update_cmd_preview).pack(anchor="w")

        ttk.Label(colM, text="Borrow Size view:").pack(anchor="w", pady=(8,0))
        for v, txt in [("absolute","Absolute"), ("delta","Δ vs Baseline")]:
            ttk.Radiobutton(colM, text=txt, value=v, variable=self.borrow_view, command=self._update_cmd_preview).pack(anchor="w")

        ttk.Label(colM, text="Δ baseline:").pack(anchor="w", pady=(8,0))
        for v, txt in [("first","First value"), ("median","Median")]:
            ttk.Radiobutton(colM, text=txt, value=v, variable=self.delta_baseline, command=self._update_cmd_preview).pack(anchor="w")

        ttk.Label(colM, text="Initial Symbol (optional):").pack(anchor="w", pady=(8,0))
        ttk.Entry(colM, textvariable=self.initial_symbol, width=20).pack(anchor="w")

        # right column
        colR = ttk.Frame(box_opts)
        colR.pack(side="left", fill="y")

        ttk.Checkbutton(colR, text="activate Borrow-Zoom", variable=self.borrow_zoom_on, command=self._update_cmd_preview).pack(anchor="w")
        ttk.Label(colR, text="Zoom-Bottom edge (0..0.9):").pack(anchor="w")
        ttk.Scale(colR, from_=0.0, to=0.9, variable=self.borrow_zoom_frac, orient="horizontal", command=lambda e: self._update_cmd_preview()).pack(fill="x")

        ttk.Label(colR, text="Borrow floor:").pack(anchor="w", pady=(8,0))
        for v, txt in [("none","No Floor"), ("p10","10th percentile"), ("min","Minimum")]:
            ttk.Radiobutton(colR, text=txt, value=v, variable=self.borrow_floor_mode, command=self._update_cmd_preview).pack(anchor="w")

        # Presets section
        box_preset = ttk.LabelFrame(frm, text="Presets", padding=10)
        box_preset.pack(fill="x", pady=8)
        rowp = ttk.Frame(box_preset)
        rowp.pack(fill="x")
        ttk.Label(rowp, text=f"File: {SETTINGS_FILE}").pack(side="left")
        ttk.Button(rowp, text="Save now", command=self._save_presets).pack(side="right")
        # ttk.Button(rowp, text="Load now", command=self._load_presets).pack(side="right", padx=6)

        # Command preview & buttons
        box_cmd = ttk.LabelFrame(frm, text="Command", padding=10)
        box_cmd.pack(fill="both", expand=True, pady=8)

        self.txt_cmd = tk.Text(box_cmd, height=4, wrap="word")
        self.txt_cmd.pack(fill="x")

        btns = ttk.Frame(box_cmd)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Run Overview only", command=self.run_overview).pack(side="left")
        ttk.Button(btns, text="Run Detail only", command=self.run_detail).pack(side="left", padx=8)
        ttk.Button(btns, text="Run Both", command=self.run_both).pack(side="left")
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")

        ttk.Label(box_cmd, text="Output:").pack(anchor="w")
        self.txt_out = tk.Text(box_cmd, height=12, wrap="word")
        self.txt_out.pack(fill="both", expand=True)
        
        ttk.Checkbutton(colR, text="Debug (print tracebacks)",
                        variable=self.debug,
                        command=self._update_cmd_preview).pack(anchor="w", pady=(8,0))

    # ---------- helpers ----------
    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=".", title="choose datafolder")
        if d:
            self.data_dir.set(d)
            self._update_cmd_preview()

    def _pick_script(self):
        f = filedialog.askopenfilename(title="choose destination script",
                                       filetypes=[("Python", "*.py"), ("All Files","*.*")])
        if f:
            self.script.set(f)
            self._update_cmd_preview()

    def _build_cmd(self, overview: bool, detail: bool):
        cmd = [sys.executable, self.script.get(),
               "--data-dir", self.data_dir.get(),
               "--days", str(self.days.get()),
               "--topN", str(self.topN.get()),
               "--overview-rank", self.overview_rank.get(),
               "--detail-order", self.detail_order.get(),
               "--date-mode", self.date_mode.get(),               
               "--x-mode", self.x_mode.get(),
               "--borrow-view", self.borrow_view.get(),
               "--delta-baseline", self.delta_baseline.get(),
               "--borrow-floor-mode", self.borrow_floor_mode.get(),
        ]
        if detail:
            cmd.append("--detail")
        if self.borrow_zoom_on.get():
            cmd += ["--borrow-zoom-frac", f"{self.borrow_zoom_frac.get():.2f}"]
        if self.initial_symbol.get().strip():
            cmd += ["--initial-symbol", self.initial_symbol.get().strip()]
        # optional CSV hints
        if self.sep.get().strip():
            cmd += ["--sep", self.sep.get().strip()]
        if self.symbol_col.get().strip():
            cmd += ["--symbol-col", self.symbol_col.get().strip()]
        if self.price_col.get().strip():
            cmd += ["--price-col", self.price_col.get().strip()]
        if self.borrow_col.get().strip():
            cmd += ["--borrow-col", self.borrow_col.get().strip()]
        if self.debug.get():
            cmd.append("--debug")

        # if only an overview is desired → the detail order doesn't matter
        if not overview and detail:
            # We always start the script the same way; the flag controls the UI at the target.
            pass
        return cmd

    def _update_cmd_preview(self):
        cmd = self._build_cmd(overview=True, detail=self.detail.get())
        s = " ".join(cmd)
        self.txt_cmd.delete("1.0", "end")
        self.txt_cmd.insert("1.0", s)
    
    def _append_output(self, text: str = "", sep: bool = False):
        """Append formatted text to the output box with optional separator."""
        if sep:
            self.txt_out.insert("end", "\n" + "-"*60 + "\n")
        self.txt_out.insert("end", text.strip() + "\n\n")
        self.txt_out.see("end")

    def _run(self, cmd):
        try:
            self.update_idletasks()
            self._append_output(f"> {' '.join(cmd)}", sep=True)
            proc = subprocess.run(cmd, capture_output=True, text=True)
            out = (proc.stdout or "") + ("\n" + (proc.stderr or ""))
            self._append_output(out)
            if proc.returncode != 0:
                messagebox.showerror("Fehler", f"Process ended with Code {proc.returncode}. See Output for details")
        except FileNotFoundError:
            messagebox.showerror("Fehler", "Python or Skript not found.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def run_overview(self):
        cmd = self._build_cmd(overview=True, detail=False)
        # The target doesn't care; it always shows Overview + optional Detail. Detail is off here.
        for flag in ("--detail","--no-overview"):
            if flag in cmd:
                cmd.remove(flag)
        self._run(cmd)

    def run_detail(self):
        cmd = self._build_cmd(overview=False, detail=True)
        if "--detail" not in cmd:
            cmd.append("--detail")
        if "--no-overview" not in cmd:
            cmd.append("--no-overview")
        self._run(cmd)

    def run_both(self):
        cmd = self._build_cmd(overview=True, detail=True)
        if "--detail" not in cmd:
            cmd.append("--detail")
        if "--no-overview" in cmd:
            cmd.remove("--no-overview")
        self._run(cmd)

    # --------- presets ---------
    def _load_presets(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                mapping = {
                    "script": self.script,
                    "data_dir": self.data_dir,
                    "days": self.days,
                    "topN": self.topN,
                    "overview_rank": self.overview_rank,
                    "detail_order": self.detail_order,
                    "detail": self.detail,
                    "x_mode": self.x_mode,
                    "borrow_view": self.borrow_view,
                    "delta_baseline": self.delta_baseline,
                    "borrow_zoom_frac": self.borrow_zoom_frac,
                    "borrow_zoom_on": self.borrow_zoom_on,
                    "borrow_floor_mode": self.borrow_floor_mode,
                    "initial_symbol": self.initial_symbol,
                    "sep": self.sep,
                    "symbol_col": self.symbol_col,
                    "price_col": self.price_col,
                    "borrow_col": self.borrow_col,
                    "date_mode": self.date_mode,
                    "debug": self.debug,

                }
                for k, v in data.items():
                    var = mapping.get(k)
                    if var is not None:
                        try:
                            var.set(v)
                        except Exception:
                            pass
                # update preview after loading
                if hasattr(self, "txt_cmd"):
                    self._update_cmd_preview()
            else:
                # nothing yet, fine
                pass
        except Exception as e:
            try:
                messagebox.showwarning("load Presets", f"Could not load presets:{e}")
            except Exception:
                pass

    def _save_presets(self):
        try:
            os.makedirs(PRESET_DIR, exist_ok=True)
            data = {
                "script": self.script.get(),
                "data_dir": self.data_dir.get(),
                "days": self.days.get(),
                "topN": self.topN.get(),
                "overview_rank": self.overview_rank.get(),
                "detail_order": self.detail_order.get(),
                "detail": self.detail.get(),
                "x_mode": self.x_mode.get(),
                "borrow_view": self.borrow_view.get(),
                "delta_baseline": self.delta_baseline.get(),
                "borrow_zoom_frac": self.borrow_zoom_frac.get(),
                "borrow_zoom_on": self.borrow_zoom_on.get(),
                "borrow_floor_mode": self.borrow_floor_mode.get(),
                "initial_symbol": self.initial_symbol.get(),
                "sep": self.sep.get(),
                "symbol_col": self.symbol_col.get(),
                "price_col": self.price_col.get(),
                "borrow_col": self.borrow_col.get(),
                "date_mode": self.date_mode.get(),
                "debug": self.debug.get(),

            }
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # optional visual hint
            if hasattr(self, "txt_out"):
                try:
                    self.txt_out.insert("end", f"Presets saved: {SETTINGS_FILE}")
                    self.txt_out.see("end")
                except Exception:
                    pass
        except Exception as e:
            try:
                messagebox.showerror("Save Presets", f"Could not save presets:{e}")
            except Exception:
                pass

    def _on_close(self):
        try:
            self._save_presets()
        finally:
            self.destroy()
            
if __name__ == "__main__":
    Launcher().mainloop()
