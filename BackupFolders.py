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
)
from tkinter.ttk import Style, Combobox, Progressbar, LabelFrame, Separator

APP_NAME = "BackupFolders"
APP_VERSION = "2.0"
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


class BackupApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION} - by Laxe4k")
        self.root.geometry("680x600")
        self.root.minsize(580, 500)
        self.root.resizable(True, True)

        self.script_dir = get_script_dir()
        self.config_path = os.path.join(self.script_dir, CONFIG_FILE)

        # State
        self.backup_dir = StringVar(value="")
        self.folders: list[str] = []
        self.compression_label = StringVar(value="5 - Normal")
        self.is_running = False

        self._load_config()
        self._build_ui()
        self._check_7zip()

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

    def _build_ui(self):
        # ── Backup destination ──
        frame_dest = LabelFrame(self.root, text="Dossier de destination des backups")
        frame_dest.pack(fill=X, padx=8, pady=4)

        self.lbl_dest = Label(
            frame_dest,
            textvariable=self.backup_dir,
            anchor=W,
            fg="#0066cc",
            cursor="hand2",
        )
        self.lbl_dest.pack(side=LEFT, fill=X, expand=True, padx=6, pady=6)
        self.lbl_dest.bind(
            "<Button-1>", lambda e: self._open_folder(self.backup_dir.get())
        )

        Button(frame_dest, text="Changer…", command=self._change_backup_dir).pack(
            side=RIGHT, padx=6, pady=6
        )

        # ── Folders list ──
        frame_folders = LabelFrame(self.root, text="Dossiers à sauvegarder")
        frame_folders.pack(fill=BOTH, expand=True, padx=8, pady=4)

        btn_bar = Frame(frame_folders)
        btn_bar.pack(fill=X, padx=4, pady=(4, 0))
        Button(btn_bar, text="Ajouter…", command=self._add_folder).pack(
            side=LEFT, padx=2
        )
        Button(btn_bar, text="Retirer", command=self._remove_folder).pack(
            side=LEFT, padx=2
        )
        Button(btn_bar, text="Tout effacer", command=self._clear_folders).pack(
            side=LEFT, padx=2
        )

        list_frame = Frame(frame_folders)
        list_frame.pack(fill=BOTH, expand=True, padx=4, pady=4)
        scrollbar = Scrollbar(list_frame)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox = Listbox(
            list_frame, yscrollcommand=scrollbar.set, selectmode="extended"
        )
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)
        self._refresh_listbox()

        # ── Compression ──
        frame_comp = LabelFrame(self.root, text="Niveau de compression")
        frame_comp.pack(fill=X, padx=8, pady=4)

        self.combo_comp = Combobox(
            frame_comp,
            textvariable=self.compression_label,
            values=list(COMPRESSION_LEVELS.keys()),
            state="readonly",
            width=40,
        )
        self.combo_comp.pack(padx=6, pady=6, anchor=W)

        # ── Progress ──
        frame_prog = Frame(self.root)
        frame_prog.pack(fill=X, padx=8, pady=4)

        self.status_var = StringVar(value="Prêt.")
        Label(frame_prog, textvariable=self.status_var, anchor=W).pack(fill=X)
        self.progress = Progressbar(frame_prog, mode="indeterminate")
        self.progress.pack(fill=X, pady=(4, 0))

        # ── Buttons ──
        frame_btns = Frame(self.root)
        frame_btns.pack(fill=X, padx=8, pady=(4, 10))

        self.btn_backup = Button(
            frame_btns,
            text="  Lancer le backup  ",
            bg="#28a745",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            command=self._start_backup,
        )
        self.btn_backup.pack(side=RIGHT, padx=4)

        Button(frame_btns, text="Quitter", command=self.root.quit).pack(
            side=LEFT, padx=4
        )

    def _refresh_listbox(self):
        self.listbox.delete(0, END)
        for f in self.folders:
            self.listbox.insert(END, f)

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
        self.btn_backup.config(state=DISABLED)
        self.progress.start(15)

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
            if os.path.exists(temp_dir):
                _force_rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)

            for folder in self.folders:
                if not os.path.isdir(folder):
                    continue
                folder_name = os.path.basename(folder) or os.path.splitdrive(folder)[
                    0
                ].replace(":", "")
                dest_sub = os.path.join(temp_dir, folder_name)
                self._set_status(f"Copie de {folder_name}…")
                shutil.copytree(
                    folder,
                    dest_sub,
                    dirs_exist_ok=True,
                    ignore_dangling_symlinks=True,
                    copy_function=_copy_ignore_missing,
                    ignore=_ignore_git_dirs,
                )

            # Compress
            compression = COMPRESSION_LEVELS.get(self.compression_label.get(), 5)
            self._set_status("Compression en cours…")
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
            if result.returncode != 0:
                self._show_error(
                    f"Erreur lors de la compression :\n{result.stderr or result.stdout}"
                )
                return

            # Move archive to destination
            self._set_status("Déplacement de l'archive…")
            shutil.move(archive_tmp, dest_path)

            self._set_status("✅ Backup terminé avec succès !")
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
        self.btn_backup.config(state=NORMAL)
        self.progress.stop()

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
    icon_path = os.path.join(get_script_dir(), "icon.ico")
    if os.path.exists(icon_path):
        root.iconbitmap(icon_path)
    BackupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
