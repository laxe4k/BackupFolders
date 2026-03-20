"""
BackupFolders - GUI Backup Tool by Laxe4k
Backs up selected folders into a 7z archive using 7-Zip.
"""

import os
import sys
import json
import shutil
import subprocess
import threading
import datetime
import getpass
import ctypes
from pathlib import Path
from tkinter import (
    Tk,
    Frame,
    Label,
    Button,
    Listbox,
    Scrollbar,
    StringVar,
    IntVar,
    PhotoImage,
    Text,
    filedialog,
    messagebox,
    END,
    BOTH,
    LEFT,
    RIGHT,
    Y,
    X,
    TOP,
    BOTTOM,
    HORIZONTAL,
    W,
    E,
    N,
    S,
    DISABLED,
    NORMAL,
    Canvas,
)
from tkinter.ttk import Style, Combobox, Progressbar, LabelFrame, Separator

APP_NAME = "BackupFolders"
APP_VERSION = "2.0.0"
CONFIG_FILE = "backup_config.json"
SEVEN_ZIP_PATH = os.path.join(
    os.environ.get("ProgramFiles", "C:\\Program Files"), "7-Zip", "7z.exe"
)

COMPRESSION_LEVELS = {
    "0 - Aucune compression (stockage)": 0,
    "1 - Très faible": 1,
    "3 - Faible": 3,
    "5 - Normal": 5,
    "7 - Élevé": 7,
    "9 - Maximum": 9,
}

# ─── Theme colors ───────────────────────────────────────────────────
BG = "#1b1b1f"  # window background
BG_CARD = "#27272b"  # sections / cards
BG_INPUT = "#313136"  # input fields, listbox
BG_HOVER = "#3c3c42"  # button hover
FG = "#e4e4e7"  # primary text
FG_DIM = "#71717a"  # secondary / muted text
FG_ACCENT = "#60a5fa"  # accent blue (links, highlights)
FG_GREEN = "#4ade80"  # success
FG_RED = "#f87171"  # danger
BORDER = "#3f3f46"  # borders
BTN_PRI = "#3b82f6"  # primary button (blue)
BTN_PRI_H = "#2563eb"  # primary button hover
BTN_OK = "#22c55e"  # green action button
BTN_OK_H = "#16a34a"  # green button hover
BTN_DNG = "#452225"  # danger button bg
BTN_DNG_H = "#5c2d30"  # danger button hover


def _copy_ignore_missing(src: str, dst: str):
    """Copy a file, silently skipping if it has vanished or is locked."""
    try:
        shutil.copy2(src, dst)
    except (FileNotFoundError, PermissionError, OSError):
        pass


def _force_rmtree(path: str):
    """Remove a directory tree, forcing removal of read-only files (e.g. .git objects)."""
    import stat

    def _on_error(_func, _path, _exc_info):
        try:
            os.chmod(_path, stat.S_IWRITE)
            os.unlink(_path)
        except OSError:
            pass

    shutil.rmtree(path, onexc=_on_error)


def _ignore_git_dirs(directory: str, entries: list[str]) -> set[str]:
    """Ignore .git directories during copytree."""
    return {e for e in entries if e == ".git"}


def get_script_dir():
    """Return the directory where the script/exe resides."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_asset_path(relative_path: str) -> str:
    """Get absolute path to a bundled asset (works for dev and PyInstaller)."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


class BackupApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("680x580")
        self.root.minsize(580, 480)
        self.root.resizable(True, True)
        self.root.configure(bg=BG)

        self.script_dir = get_script_dir()
        self.config_path = os.path.join(self.script_dir, CONFIG_FILE)

        # State
        self.backup_dir = StringVar(value="")
        self.folders: list[str] = []
        self.compression_label = StringVar(value="5 - Normal")
        self.is_running = False
        self._img_refs: list[PhotoImage] = []

        self._setup_theme()
        self._load_icons()
        self._load_config()
        self._build_ui()
        self._check_7zip()

    def _setup_theme(self):
        style = Style()
        style.theme_use("clam")
        style.configure(
            ".", background=BG, foreground=FG, fieldbackground=BG_INPUT, borderwidth=0
        )
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure(
            "TLabelframe",
            background=BG_CARD,
            foreground=FG_ACCENT,
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "TLabelframe.Label",
            background=BG_CARD,
            foreground=FG_ACCENT,
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "TCombobox",
            fieldbackground=BG_INPUT,
            background=BG_INPUT,
            foreground=FG,
            arrowcolor=FG_ACCENT,
            borderwidth=1,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", BG_INPUT)],
            selectbackground=[("readonly", BG_INPUT)],
            selectforeground=[("readonly", FG)],
        )
        style.configure(
            "green.Horizontal.TProgressbar",
            troughcolor=BG_INPUT,
            background=FG_GREEN,
            thickness=5,
        )
        style.configure("TSeparator", background=BORDER)

    def _load_icons(self):
        icons_dir = os.path.join("assets", "icons")
        names = {
            "archive": "box-archive-solid-full.png",
            "folder_open": "folder-open-solid-full.png",
            "folder_plus": "folder-plus-solid-full.png",
            "folder_minus": "folder-minus-solid-full.png",
            "trash": "trash-can-solid-full.png",
            "play": "play-solid-full.png",
            "zipper": "file-zipper-solid-full.png",
            "folder_closed": "folder-closed-solid-full.png",
        }
        self.icons: dict[str, PhotoImage | None] = {}
        for key, filename in names.items():
            path = _get_asset_path(os.path.join(icons_dir, filename))
            if os.path.isfile(path):
                self.icons[key] = PhotoImage(file=path)
            else:
                self.icons[key] = None

    # ─── Config persistence ─────────────────────────────────────────────

    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.backup_dir.set(data.get("backup_dir", ""))
                self.folders = data.get("folders", [])
                self.compression_label.set(data.get("compression", "5 - Normal"))
            except (json.JSONDecodeError, OSError):
                pass
        # Migration: import from old .bat config files
        if not self.backup_dir.get():
            old_dir_file = os.path.join(self.script_dir, "BackupDir.txt")
            if os.path.exists(old_dir_file):
                with open(old_dir_file, "r", encoding="utf-8") as f:
                    self.backup_dir.set(f.read().strip())
        if not self.folders:
            old_folders_file = os.path.join(self.script_dir, "Folders.txt")
            if os.path.exists(old_folders_file):
                with open(old_folders_file, "r", encoding="utf-8") as f:
                    self.folders = [line.strip() for line in f if line.strip()]

    def _save_config(self):
        data = {
            "backup_dir": self.backup_dir.get(),
            "folders": self.folders,
            "compression": self.compression_label.get(),
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ─── UI ─────────────────────────────────────────────────────────────

    def _make_btn(
        self,
        parent,
        text,
        command,
        bg=BG_INPUT,
        fg=FG,
        hover_bg=BG_HOVER,
        font=("Segoe UI", 9),
        icon_key=None,
        **kw,
    ):
        icon = self.icons.get(icon_key) if icon_key else None
        btn = Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            font=font,
            image=icon if icon else "",
            compound=LEFT if icon else "none",
            **kw,
        )
        if icon:
            self._img_refs.append(icon)
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    def _build_ui(self):
        pad = Frame(self.root, bg=BG)
        pad.pack(fill=BOTH, expand=True, padx=14, pady=10)

        # ── Header ──
        hdr = Frame(pad, bg=BG)
        hdr.pack(fill=X, pady=(0, 8))
        icon = self.icons.get("archive")
        if icon:
            l = Label(hdr, image=icon, bg=BG)
            self._img_refs.append(icon)
            l.pack(side=LEFT, padx=(0, 8))
        tf = Frame(hdr, bg=BG)
        tf.pack(side=LEFT)
        Label(tf, text=APP_NAME, font=("Segoe UI Semibold", 15), bg=BG, fg=FG).pack(
            anchor=W
        )
        Label(
            tf, text=f"v{APP_VERSION} · Laxe4k", font=("Segoe UI", 8), bg=BG, fg=FG_DIM
        ).pack(anchor=W)

        # ── Destination (compact) ──
        dest_row = Frame(
            pad, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1
        )
        dest_row.pack(fill=X, pady=(0, 6), ipady=2)
        Label(
            dest_row,
            text="Destination",
            font=("Segoe UI Semibold", 9),
            bg=BG_CARD,
            fg=FG_ACCENT,
        ).pack(side=LEFT, padx=(8, 6))
        self.lbl_dest = Label(
            dest_row,
            textvariable=self.backup_dir,
            anchor=W,
            fg=FG,
            bg=BG_CARD,
            cursor="hand2",
            font=("Segoe UI", 9),
        )
        self.lbl_dest.pack(side=LEFT, fill=X, expand=True)
        self.lbl_dest.bind(
            "<Button-1>", lambda e: self._open_folder(self.backup_dir.get())
        )
        self._make_btn(
            dest_row,
            "Changer…",
            self._change_backup_dir,
            bg=BTN_PRI,
            fg="white",
            hover_bg=BTN_PRI_H,
            icon_key="folder_open",
        ).pack(side=RIGHT, padx=4, pady=2)

        # ── Folders list ──
        fbox = Frame(pad, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        fbox.pack(fill=BOTH, expand=True, pady=(0, 6))

        top_bar = Frame(fbox, bg=BG_CARD)
        top_bar.pack(fill=X, padx=8, pady=(6, 4))
        Label(
            top_bar,
            text="Dossiers à sauvegarder",
            font=("Segoe UI Semibold", 9),
            bg=BG_CARD,
            fg=FG_ACCENT,
        ).pack(side=LEFT)
        self.lbl_count = Label(
            top_bar, text="0", bg=BG_CARD, fg=FG_DIM, font=("Segoe UI", 8)
        )
        self.lbl_count.pack(side=RIGHT)

        btn_bar = Frame(fbox, bg=BG_CARD)
        btn_bar.pack(fill=X, padx=8, pady=(0, 4))
        self._make_btn(
            btn_bar,
            "Ajouter",
            self._add_folder,
            bg=BTN_PRI,
            fg="white",
            hover_bg=BTN_PRI_H,
            icon_key="folder_plus",
        ).pack(side=LEFT, padx=(0, 4))
        self._make_btn(
            btn_bar, "Retirer", self._remove_folder, icon_key="folder_minus"
        ).pack(side=LEFT, padx=(0, 4))
        self._make_btn(
            btn_bar,
            "Tout vider",
            self._clear_folders,
            bg=BTN_DNG,
            fg=FG_RED,
            hover_bg=BTN_DNG_H,
            icon_key="trash",
        ).pack(side=LEFT)

        lf = Frame(fbox, bg=BG_CARD)
        lf.pack(fill=BOTH, expand=True, padx=8, pady=(0, 6))
        sb = Scrollbar(
            lf, bg=BG_INPUT, troughcolor=BG_CARD, activebackground=FG_DIM, width=8
        )
        sb.pack(side=RIGHT, fill=Y)
        self.listbox = Listbox(
            lf,
            yscrollcommand=sb.set,
            selectmode="extended",
            bg=BG_INPUT,
            fg=FG,
            selectbackground=FG_ACCENT,
            selectforeground=BG,
            font=("Consolas", 9),
            bd=0,
            highlightthickness=1,
            highlightcolor=FG_ACCENT,
            highlightbackground=BORDER,
            activestyle="none",
        )
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)
        sb.config(command=self.listbox.yview)
        self._refresh_listbox()

        # ── Bottom: compression + backup ──
        bot = Frame(pad, bg=BG)
        bot.pack(fill=X, pady=(0, 4))
        zipper = self.icons.get("zipper")
        cl = Label(
            bot,
            text="Compression",
            bg=BG,
            fg=FG_DIM,
            font=("Segoe UI", 8),
            image=zipper if zipper else "",
            compound=LEFT if zipper else "none",
        )
        if zipper:
            self._img_refs.append(zipper)
        cl.pack(side=LEFT, padx=(0, 4))
        self.combo_comp = Combobox(
            bot,
            textvariable=self.compression_label,
            values=list(COMPRESSION_LEVELS.keys()),
            state="readonly",
            width=30,
        )
        self.combo_comp.pack(side=LEFT)
        self.btn_backup = self._make_btn(
            bot,
            " Lancer le backup ",
            self._start_backup,
            bg=BTN_OK,
            fg="white",
            hover_bg=BTN_OK_H,
            font=("Segoe UI Semibold", 10),
            icon_key="play",
        )
        self.btn_backup.pack(side=RIGHT)

        # ── Status ──
        Separator(pad).pack(fill=X, pady=(6, 4))
        sf = Frame(pad, bg=BG)
        sf.pack(fill=X)
        status_row = Frame(sf, bg=BG)
        status_row.pack(fill=X)
        self.status_var = StringVar(value="Prêt.")
        Label(
            status_row,
            textvariable=self.status_var,
            anchor=W,
            bg=BG,
            fg=FG_DIM,
            font=("Segoe UI", 8),
        ).pack(side=LEFT, fill=X, expand=True)
        self._details_visible = False
        self.btn_details = Button(
            status_row,
            text="Détails ▸",
            command=self._toggle_details,
            bg=BG,
            fg=FG_DIM,
            activebackground=BG_HOVER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=6,
            pady=0,
            cursor="hand2",
            font=("Segoe UI", 8),
        )
        self.btn_details.pack(side=RIGHT)
        self.btn_details.bind(
            "<Enter>", lambda e: self.btn_details.config(fg=FG_ACCENT)
        )
        self.btn_details.bind("<Leave>", lambda e: self.btn_details.config(fg=FG_DIM))
        self.progress = Progressbar(
            sf,
            mode="determinate",
            style="green.Horizontal.TProgressbar",
            maximum=100,
        )
        self.progress.pack(fill=X, pady=(2, 0))
        # ── Details log panel (hidden by default) ──
        self.details_frame = Frame(
            pad, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1
        )
        self.log_text = Text(
            self.details_frame,
            bg=BG_INPUT,
            fg=FG_DIM,
            font=("Consolas", 8),
            bd=0,
            highlightthickness=0,
            wrap="word",
            height=8,
            state=DISABLED,
            cursor="arrow",
        )
        log_sb = Scrollbar(
            self.details_frame,
            command=self.log_text.yview,
            bg=BG_INPUT,
            troughcolor=BG_CARD,
            width=8,
        )
        self.log_text.config(yscrollcommand=log_sb.set)
        log_sb.pack(side=RIGHT, fill=Y)
        self.log_text.pack(fill=BOTH, expand=True, padx=1, pady=1)

    def _refresh_listbox(self):
        self.listbox.delete(0, END)
        for f in self.folders:
            self.listbox.insert(END, f)
        n = len(self.folders)
        self.lbl_count.config(text=f"{n} dossier{'s' if n != 1 else ''}")

    def _toggle_details(self):
        if self._details_visible:
            self.details_frame.pack_forget()
            self.btn_details.config(text="Détails ▸")
        else:
            self.details_frame.pack(fill=BOTH, expand=False, pady=(4, 0))
            self.btn_details.config(text="Détails ▾")
        self._details_visible = not self._details_visible

    def _log(self, text: str):
        def _append():
            self.log_text.config(state=NORMAL)
            self.log_text.insert(END, text + "\n")
            self.log_text.see(END)
            self.log_text.config(state=DISABLED)

        self.root.after(0, _append)

    def _update_progress(self, value: float):
        self.root.after(0, lambda: self.progress.config(value=min(value, 100)))

    # ─── Actions ────────────────────────────────────────────────────────

    def _change_backup_dir(self):
        d = filedialog.askdirectory(
            title="Choisir le dossier de destination des backups",
            initialdir=self.backup_dir.get() or self.script_dir,
        )
        if d:
            self.backup_dir.set(os.path.normpath(d))
            self._save_config()

    def _add_folder(self):
        d = filedialog.askdirectory(title="Ajouter un dossier à sauvegarder")
        if d:
            norm = os.path.normpath(d)
            if norm not in self.folders:
                self.folders.append(norm)
                self._refresh_listbox()
                self._save_config()

    def _remove_folder(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        for idx in reversed(sel):
            del self.folders[idx]
        self._refresh_listbox()
        self._save_config()

    def _clear_folders(self):
        if not self.folders:
            return
        if messagebox.askyesno("Confirmer", "Effacer tous les dossiers de la liste ?"):
            self.folders.clear()
            self._refresh_listbox()
            self._save_config()

    def _open_folder(self, path: str):
        if path and os.path.isdir(path):
            os.startfile(path)

    def _check_7zip(self):
        if not os.path.isfile(SEVEN_ZIP_PATH):
            self.status_var.set(
                "⚠ 7-Zip non détecté. Il sera installé au premier backup."
            )

    # ─── Backup logic ───────────────────────────────────────────────────

    def _start_backup(self):
        if self.is_running:
            return

        # Validations
        backup_dir = self.backup_dir.get()
        if not backup_dir or not os.path.isdir(backup_dir):
            messagebox.showerror(
                "Erreur",
                "Le dossier de destination n'existe pas.\nVeuillez le configurer.",
            )
            return
        if not self.folders:
            messagebox.showerror(
                "Erreur", "Aucun dossier à sauvegarder.\nAjoutez-en au moins un."
            )
            return

        username = getpass.getuser()
        today = datetime.date.today().strftime("%Y-%m-%d")
        archive_name = f"Backup-{username}_{today}.7z"
        dest_path = os.path.join(backup_dir, archive_name)

        if os.path.exists(dest_path):
            messagebox.showwarning(
                "Attention", "Un backup a déjà été effectué aujourd'hui."
            )
            return

        self._save_config()
        self.is_running = True
        self.btn_backup.config(state=DISABLED, bg=BG_HOVER)
        self.progress.config(value=0)
        # Clear log
        self.log_text.config(state=NORMAL)
        self.log_text.delete("1.0", END)
        self.log_text.config(state=DISABLED)
        self._log(f"Démarrage du backup — {dest_path}")

        threading.Thread(
            target=self._run_backup, args=(dest_path, today, username), daemon=True
        ).start()

    def _run_backup(self, dest_path: str, today: str, username: str):
        temp_dir = os.path.join(
            os.environ.get(
                "TEMP",
                os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp"),
            ),
            ".Backup",
            f"Backup-{username}_{today}",
        )
        try:
            # Install 7-Zip if missing
            if not os.path.isfile(SEVEN_ZIP_PATH):
                self._set_status("Installation de 7-Zip…")
                ret = subprocess.run(
                    [
                        "winget",
                        "install",
                        "--id",
                        "7zip.7zip",
                        "--exact",
                        "--source",
                        "winget",
                        "--accept-source-agreements",
                        "--force",
                    ],
                    capture_output=True,
                    text=True,
                )
                if not os.path.isfile(SEVEN_ZIP_PATH):
                    self._show_error(
                        "7-Zip n'a pas pu être installé.\nInstallez-le manuellement depuis https://www.7-zip.org/"
                    )
                    return

            # Copy folders
            self._set_status("Copie des fichiers…")
            self._log("Préparation du dossier temporaire…")
            if os.path.exists(temp_dir):
                _force_rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)

            valid_folders = [f for f in self.folders if os.path.isdir(f)]
            total_folders = len(valid_folders)
            if total_folders == 0:
                self._set_status("Aucun dossier valide à sauvegarder.")
                self._log(
                    "Aucun dossier valide trouvé dans la configuration. Abandon du backup."
                )
                try:
                    _force_rmtree(temp_dir)
                except Exception:
                    pass
                self._show_error(
                    "Aucun des dossiers configurés n'existe ou n'est accessible.\n"
                    "Vérifiez la configuration de vos dossiers avant de relancer le backup."
                )
                return
            for i, folder in enumerate(valid_folders):
                folder_name = os.path.basename(folder) or os.path.splitdrive(folder)[
                    0
                ].replace(":", "")
                dest_sub = os.path.join(temp_dir, folder_name)
                self._set_status(f"Copie de {folder_name}… ({i + 1}/{total_folders})")
                self._log(f"  Copie : {folder}")
                shutil.copytree(
                    folder,
                    dest_sub,
                    dirs_exist_ok=True,
                    ignore_dangling_symlinks=True,
                    copy_function=_copy_ignore_missing,
                    ignore=_ignore_git_dirs,
                )
                self._update_progress(
                    70 * (i + 1) / total_folders if total_folders else 70
                )

            # Compress
            compression = COMPRESSION_LEVELS.get(self.compression_label.get(), 5)
            self._set_status("Compression en cours…")
            self._log(f"  Compression (niveau {compression})…")
            self._update_progress(80)
            archive_tmp = temp_dir + ".7z"
            result = subprocess.run(
                [
                    SEVEN_ZIP_PATH,
                    "a",
                    "-t7z",
                    archive_tmp,
                    "-r",
                    temp_dir,
                    f"-mx={compression}",
                ],
                capture_output=True,
                text=True,
            )
            self._update_progress(90)
            if result.returncode != 0:
                self._log(f"  ERREUR 7-Zip : {result.stderr or result.stdout}")
                self._show_error(
                    f"Erreur lors de la compression :\n{result.stderr or result.stdout}"
                )
                return
            self._log("  Compression terminée.")

            # Move archive to destination
            self._set_status("Déplacement de l'archive…")
            self._log(f"  Déplacement vers {dest_path}")
            shutil.move(archive_tmp, dest_path)
            self._update_progress(100)

            try:
                size_mb = os.path.getsize(dest_path) / (1024 * 1024)
                self._log(f"  Archive : {size_mb:.1f} Mo")
            except OSError:
                pass

            self._set_status("✅ Backup terminé avec succès !")
            self._log("✅ Backup terminé avec succès !")
            self._show_info(f"Backup terminé !\n\n{dest_path}")

        except Exception as exc:
            self._show_error(f"Erreur inattendue :\n{exc}")
        finally:
            # Cleanup
            if os.path.exists(temp_dir):
                try:
                    _force_rmtree(temp_dir)
                except OSError:
                    pass
            self.root.after(0, self._finish_backup)

    def _finish_backup(self):
        self.is_running = False
        self.btn_backup.config(state=NORMAL, bg=BTN_OK)

    # ─── Thread-safe UI helpers ─────────────────────────────────────────

    def _set_status(self, text: str):
        self.root.after(0, lambda: self.status_var.set(text))

    def _show_error(self, msg: str):
        self.root.after(0, lambda: messagebox.showerror("Erreur", msg))

    def _show_info(self, msg: str):
        self.root.after(0, lambda: messagebox.showinfo("Succès", msg))


def run_auto():
    """Run backup in auto mode (no GUI) for task scheduler compatibility."""
    app_dir = get_script_dir()
    config_path = os.path.join(app_dir, CONFIG_FILE)
    if not os.path.exists(config_path):
        print("Aucune configuration trouvée.")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    backup_dir = data.get("backup_dir", "")
    folders = data.get("folders", [])
    compression_label = data.get("compression", "5 - Normal")
    compression = COMPRESSION_LEVELS.get(compression_label, 5)

    if not backup_dir or not os.path.isdir(backup_dir):
        print("Dossier de destination invalide.")
        sys.exit(1)
    if not folders:
        print("Aucun dossier à sauvegarder.")
        sys.exit(1)

    username = getpass.getuser()
    today = datetime.date.today().strftime("%Y-%m-%d")
    archive_name = f"Backup-{username}_{today}.7z"
    dest_path = os.path.join(backup_dir, archive_name)

    if os.path.exists(dest_path):
        print("Un backup a déjà été effectué aujourd'hui.")
        sys.exit(0)

    if not os.path.isfile(SEVEN_ZIP_PATH):
        print("7-Zip non installé.")
        sys.exit(1)

    temp_dir = os.path.join(
        os.environ.get("TEMP", ""), ".Backup", f"Backup-{username}_{today}"
    )
    try:
        if os.path.exists(temp_dir):
            _force_rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        for folder in folders:
            if not os.path.isdir(folder):
                continue
            folder_name = os.path.basename(folder) or os.path.splitdrive(folder)[
                0
            ].replace(":", "")
            shutil.copytree(
                folder,
                os.path.join(temp_dir, folder_name),
                dirs_exist_ok=True,
                ignore_dangling_symlinks=True,
                copy_function=_copy_ignore_missing,
                ignore=_ignore_git_dirs,
            )

        archive_tmp = temp_dir + ".7z"
        subprocess.run(
            [
                SEVEN_ZIP_PATH,
                "a",
                "-t7z",
                archive_tmp,
                "-r",
                temp_dir,
                f"-mx={compression}",
            ],
            check=True,
        )
        shutil.move(archive_tmp, dest_path)
        print(f"Backup terminé : {dest_path}")
    finally:
        if os.path.exists(temp_dir):
            try:
                _force_rmtree(temp_dir)
            except OSError:
                pass


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "-auto":
        run_auto()
        return

    root = Tk()
    # Set icon if available
    icon_path = _get_asset_path(os.path.join("assets", "icons", "icon.ico"))
    if os.path.exists(icon_path):
        root.iconbitmap(icon_path)

    # Dark title bar (Windows 11)
    def _apply_dark_titlebar():
        try:
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            # Enable dark mode
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                20,
                ctypes.byref(ctypes.c_int(1)),
                ctypes.sizeof(ctypes.c_int),
            )
            # Set caption color to BG (#28282c → COLORREF BGR 0x2c2828)
            color = ctypes.c_uint32(0x2C2828)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                35,
                ctypes.byref(color),
                ctypes.sizeof(color),
            )
            # Force redraw title bar
            root.withdraw()
            root.deiconify()
        except Exception:
            pass

    root.after(50, _apply_dark_titlebar)
    BackupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
