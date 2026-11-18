//! Backup Folders — port Rust / egui (eframe 0.29).
//! Interface graphique Windows (egui, zéro dépendance système) + mode console (-auto).
//! Logique de backup identique à l'original Python : copie des dossiers (.git ignoré),
//! compression 7z via NanaZip, config persistante en JSON, progression et logs.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use chrono::Local;
use eframe::egui::{self, Align, Color32, FontFamily, FontId, Layout, RichText, Stroke, TextStyle};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;
use walkdir::WalkDir;

const APP_NAME: &str = "Backup Folders";
const APP_VERSION: &str = "3.0.0";
const CONFIG_FILE: &str = "backup_config.json";
const DEFAULT_COMPRESSION: &str = "5 - Normale";

// ── Palette ──
const BG: Color32 = Color32::from_rgb(14, 16, 21);
const SIDE: Color32 = Color32::from_rgb(20, 23, 29);
const ROW: Color32 = Color32::from_rgb(28, 32, 41);
const BORDER: Color32 = Color32::from_rgb(42, 47, 58);
const ACCENT: Color32 = Color32::from_rgb(83, 172, 106);
const ACCENT_DIM: Color32 = Color32::from_rgb(42, 86, 53);
const MUTED: Color32 = Color32::from_rgb(136, 144, 158);
const WARN: Color32 = Color32::from_rgb(251, 191, 36);
const ERR: Color32 = Color32::from_rgb(248, 113, 113);

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
struct Config {
    backup_dir: String,
    folders: Vec<String>,
    compression: String, // ex: "5 - Normale"
}

const COMPRESSION_LEVELS: &[(&str, i32)] = &[
    ("0 - Aucune", 0),
    ("1 - Le plus rapide", 1),
    ("3 - Rapide", 3),
    ("5 - Normale", 5),
    ("7 - Maximum", 7),
    ("9 - Ultra", 9),
    ("Ultra - Highest (Ultimate)", -1),
];

enum WorkerMsg {
    Status(String),
    Progress(f64),
    Log(String),
    Done(Result<(), String>),
}

#[derive(PartialEq, Clone, Copy)]
enum Tab {
    Folders,
    Journal,
}

struct BackupApp {
    config: Config,
    rx: Option<mpsc::Receiver<WorkerMsg>>,
    running: bool,
    status: String,
    progress: f32,
    log: String,
    tab: Tab,
}

// ════════════════════════════════════════════════════════════════════════════════
// Thème
// ════════════════════════════════════════════════════════════════════════════════

fn setup_style(ctx: &egui::Context) {
    let mut v = egui::Visuals::dark();
    v.panel_fill = BG;
    v.window_fill = SIDE;
    v.extreme_bg_color = ROW;
    v.selection.bg_fill = ACCENT_DIM;
    v.selection.stroke = Stroke::new(1.0_f32, Color32::WHITE);
    v.widgets.noninteractive.bg_stroke = Stroke::new(1.0_f32, BORDER);

    let radius = egui::Rounding::same(8.0);
    for w in [
        &mut v.widgets.noninteractive,
        &mut v.widgets.inactive,
        &mut v.widgets.hovered,
        &mut v.widgets.active,
        &mut v.widgets.open,
    ] {
        w.rounding = radius;
    }
    v.widgets.inactive.weak_bg_fill = Color32::from_rgb(34, 39, 50);
    v.widgets.inactive.bg_fill = Color32::from_rgb(34, 39, 50);
    v.widgets.hovered.weak_bg_fill = Color32::from_rgb(46, 53, 68);
    v.widgets.hovered.bg_stroke = Stroke::new(1.0_f32, ACCENT);
    v.widgets.active.weak_bg_fill = ACCENT_DIM;

    ctx.style_mut(|s| {
        s.visuals = v;
        s.spacing.item_spacing = egui::vec2(8.0, 8.0);
        s.spacing.button_padding = egui::vec2(12.0, 6.0);
        s.text_styles = [
            (TextStyle::Heading, FontId::new(22.0, FontFamily::Proportional)),
            (TextStyle::Body, FontId::new(14.5, FontFamily::Proportional)),
            (TextStyle::Button, FontId::new(14.5, FontFamily::Proportional)),
            (TextStyle::Small, FontId::new(12.0, FontFamily::Proportional)),
            (TextStyle::Monospace, FontId::new(12.5, FontFamily::Monospace)),
        ]
        .into();
    });
}

fn muted(t: impl Into<String>) -> RichText {
    RichText::new(t.into()).color(MUTED)
}

fn caption(ui: &mut egui::Ui, t: &str) {
    ui.add_space(6.0);
    ui.label(RichText::new(t).strong().size(11.5).color(MUTED));
}

// ════════════════════════════════════════════════════════════════════════════════
// App
// ════════════════════════════════════════════════════════════════════════════════

impl BackupApp {
    fn new(cc: &eframe::CreationContext<'_>) -> Self {
        setup_style(&cc.egui_ctx);
        egui_extras::install_image_loaders(&cc.egui_ctx);
        let mut config = load_config();
        if !COMPRESSION_LEVELS
            .iter()
            .any(|(l, _)| *l == config.compression)
        {
            config.compression = DEFAULT_COMPRESSION.to_string();
        }
        Self {
            config,
            rx: None,
            running: false,
            status: "Prêt.".to_string(),
            progress: 0.0,
            log: String::new(),
            tab: Tab::Folders,
        }
    }

    fn add_folder(&mut self, path: String) {
        if !self.config.folders.contains(&path) {
            self.config.folders.push(path);
            save_config(&self.config);
        }
    }

    fn start_backup(&mut self) {
        let backup_dir = PathBuf::from(&self.config.backup_dir);
        if !backup_dir.is_dir() {
            let _ = rfd::MessageDialog::new()
                .set_title("Erreur")
                .set_description("Le dossier de destination n'existe pas.\nVeuillez le configurer.")
                .set_level(rfd::MessageLevel::Error)
                .show();
            return;
        }
        if self.config.folders.is_empty() {
            let _ = rfd::MessageDialog::new()
                .set_title("Erreur")
                .set_description("Aucun dossier à sauvegarder.\nAjoutez-en au moins un.")
                .set_level(rfd::MessageLevel::Error)
                .show();
            return;
        }

        let username = std::env::var("USERNAME").unwrap_or_else(|_| "utilisateur".into());
        let today = Local::now().format("%Y-%m-%d").to_string();
        let archive_name = format!("Backup-{username}_{today}.7z");
        let dest_path = backup_dir.join(&archive_name);

        if dest_path.exists() {
            let _ = rfd::MessageDialog::new()
                .set_title("Attention")
                .set_description("Un backup a déjà été effectué aujourd'hui.")
                .show();
            return;
        }

        save_config(&self.config);
        self.running = true;
        self.status = format!("Démarrage du backup — {}", dest_path.display());
        self.progress = 0.0;
        self.log = format!("Démarrage du backup — {}\n", dest_path.display());

        let folders = self.config.folders.clone();
        let compression_label = self.config.compression.clone();
        let compression = COMPRESSION_LEVELS
            .iter()
            .find(|(l, _)| *l == compression_label)
            .map(|(_, level)| *level)
            .unwrap_or(5);
        let temp_dir = std::env::temp_dir()
            .join(".Backup")
            .join(format!("Backup-{username}_{today}"));

        // Nouveau canal à chaque backup (l'ancien code paniquait au 2e lancement).
        let (tx, rx) = mpsc::channel();
        self.rx = Some(rx);
        let tx_status = tx.clone();
        let tx_progress = tx.clone();
        let tx_log = tx.clone();
        let tx_done = tx;

        thread::spawn(move || {
            let result = run_backup_core(
                &folders,
                &temp_dir,
                &dest_path,
                compression,
                move |s| {
                    let _ = tx_status.send(WorkerMsg::Status(s.to_string()));
                },
                move |p| {
                    let _ = tx_progress.send(WorkerMsg::Progress(p));
                },
                move |s| {
                    let _ = tx_log.send(WorkerMsg::Log(s.to_string()));
                },
            );

            force_rmtree(&temp_dir);

            let _ = tx_done.send(WorkerMsg::Done(result));
        });
    }

    fn drain_worker(&mut self) {
        let Some(rx) = &self.rx else { return };
        let mut done: Option<Result<(), String>> = None;
        while let Ok(msg) = rx.try_recv() {
            match msg {
                WorkerMsg::Status(s) => self.status = s,
                WorkerMsg::Progress(p) => self.progress = p as f32,
                WorkerMsg::Log(l) => {
                    self.log.push_str(&l);
                    self.log.push('\n');
                }
                WorkerMsg::Done(result) => done = Some(result),
            }
        }
        if let Some(result) = done {
            self.running = false;
            match result {
                Ok(()) => {
                    self.status = "✅ Backup terminé avec succès !".to_string();
                    self.progress = 100.0;
                    let _ = rfd::MessageDialog::new()
                        .set_title("Succès")
                        .set_description(format!("Backup terminé !\n\n{}", self.config.backup_dir))
                        .show();
                }
                Err(e) => {
                    self.status = format!("❌ Erreur : {e}");
                    let _ = rfd::MessageDialog::new()
                        .set_title("Erreur")
                        .set_description(&e)
                        .set_level(rfd::MessageLevel::Error)
                        .show();
                }
            }
        }
    }

    // ── Panneau latéral : réglages + lancement ──
    fn ui_side(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.add(
                egui::Image::new(egui::include_image!("../assets/logo.png"))
                    .fit_to_exact_size(egui::vec2(34.0, 34.0)),
            );
            ui.vertical(|ui| {
                ui.spacing_mut().item_spacing.y = 0.0;
                ui.label(RichText::new(APP_NAME).strong().size(18.0));
                ui.label(muted(format!("v{APP_VERSION} · Axioneer")).small());
            });
        });
        ui.add_space(8.0);
        ui.separator();

        // Destination
        caption(ui, "DESTINATION");
        let empty = self.config.backup_dir.is_empty();
        let valid = Path::new(&self.config.backup_dir).is_dir();
        egui::Frame::none()
            .fill(ROW)
            .rounding(8.0)
            .inner_margin(10.0)
            .show(ui, |ui| {
                ui.set_width(ui.available_width());
                let (text, color) = if empty {
                    ("Aucun dossier choisi".to_string(), MUTED)
                } else if !valid {
                    (self.config.backup_dir.clone(), ERR)
                } else {
                    (self.config.backup_dir.clone(), Color32::WHITE)
                };
                ui.add(egui::Label::new(RichText::new(text).monospace().color(color)).truncate())
                    .on_hover_text(&self.config.backup_dir);
            });
        if ui
            .add_sized([ui.available_width(), 30.0], egui::Button::new("📂  Changer…"))
            .clicked()
        {
            let mut dialog =
                rfd::FileDialog::new().set_title("Choisir le dossier de destination des backups");
            if valid {
                dialog = dialog.set_directory(Path::new(&self.config.backup_dir));
            }
            if let Some(path) = dialog.pick_folder() {
                self.config.backup_dir = path.to_string_lossy().to_string();
                save_config(&self.config);
            }
        }

        // Compression
        caption(ui, "COMPRESSION");
        egui::ComboBox::from_id_salt("compression")
            .width(ui.available_width())
            .selected_text(&self.config.compression)
            .show_ui(ui, |ui| {
                for (name, _) in COMPRESSION_LEVELS {
                    let selected = self.config.compression == *name;
                    if ui.selectable_label(selected, *name).clicked() && !selected {
                        self.config.compression = (*name).to_string();
                        save_config(&self.config);
                    }
                }
            });

        // Bas du panneau : statut, progression, bouton
        ui.with_layout(Layout::bottom_up(Align::Min), |ui| {
            let w = ui.available_width();
            let label = if self.running {
                "⏳  Backup en cours…"
            } else {
                "🚀  Lancer le backup"
            };
            let btn = egui::Button::new(RichText::new(label).strong().size(15.0).color(BG))
                .fill(ACCENT)
                .min_size(egui::vec2(w, 44.0));
            if ui.add_enabled(!self.running, btn).clicked() {
                self.start_backup();
            }

            ui.add(
                egui::ProgressBar::new((self.progress / 100.0).clamp(0.0, 1.0))
                    .desired_height(18.0)
                    .fill(ACCENT)
                    .animate(self.running)
                    .text(RichText::new(format!("{:.0}%", self.progress)).small().strong()),
            );

            let dot = if self.running {
                WARN
            } else if self.status.starts_with('✅') {
                ACCENT
            } else if self.status.starts_with('❌') {
                ERR
            } else {
                MUTED
            };
            ui.horizontal(|ui| {
                let (rect, _) = ui.allocate_exact_size(egui::vec2(10.0, 10.0), egui::Sense::hover());
                ui.painter().circle_filled(rect.center(), 4.0, dot);
                ui.add(egui::Label::new(muted(&self.status)).truncate())
                    .on_hover_text(&self.status);
            });
        });
    }

    // ── Zone principale : onglets ──
    fn ui_main(&mut self, ui: &mut egui::Ui) {
        let n = self.config.folders.len();
        ui.horizontal(|ui| {
            ui.selectable_value(&mut self.tab, Tab::Folders, format!("📁  Dossiers ({n})"));
            ui.selectable_value(&mut self.tab, Tab::Journal, "📜  Journal");
        });
        ui.separator();
        match self.tab {
            Tab::Folders => self.ui_folders(ui),
            Tab::Journal => self.ui_journal(ui),
        }
    }

    fn ui_folders(&mut self, ui: &mut egui::Ui) {
        let n = self.config.folders.len();
        ui.horizontal(|ui| {
            if ui.button("➕  Ajouter").clicked() {
                if let Some(path) = rfd::FileDialog::new()
                    .set_title("Ajouter un dossier à sauvegarder")
                    .pick_folder()
                {
                    self.add_folder(path.to_string_lossy().to_string());
                }
            }
            if ui.add_enabled(n > 0, egui::Button::new("🗑  Tout vider")).clicked() {
                self.config.folders.clear();
                save_config(&self.config);
            }
            ui.label(muted("ou glissez-déposez des dossiers"));
        });

        let mut to_remove: Option<usize> = None;
        egui::ScrollArea::vertical()
            .auto_shrink([false, false])
            .show(ui, |ui| {
                ui.spacing_mut().item_spacing.y = 6.0;
                if n == 0 {
                    ui.add_space(60.0);
                    ui.vertical_centered(|ui| {
                        ui.label(RichText::new("📥").size(44.0));
                        ui.label(muted("Aucun dossier à sauvegarder"));
                    });
                    return;
                }
                for (i, folder) in self.config.folders.iter().enumerate() {
                    let p = Path::new(folder);
                    let exists = p.is_dir();
                    let name = p
                        .file_name()
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_else(|| folder.clone());
                    let parent = p
                        .parent()
                        .map(|x| x.to_string_lossy().to_string())
                        .unwrap_or_default();
                    egui::Frame::none()
                        .fill(ROW)
                        .rounding(8.0)
                        .inner_margin(egui::Margin::symmetric(12.0, 8.0))
                        .show(ui, |ui| {
                            ui.set_width(ui.available_width());
                            ui.horizontal(|ui| {
                                ui.label(RichText::new(if exists { "📁" } else { "⚠" }).size(20.0));
                                ui.vertical(|ui| {
                                    ui.set_max_width((ui.available_width() - 36.0).max(50.0));
                                    ui.spacing_mut().item_spacing.y = 1.0;
                                    let c = if exists { Color32::WHITE } else { ERR };
                                    ui.add(egui::Label::new(RichText::new(name).strong().color(c)).truncate())
                                        .on_hover_text(folder);
                                    if !parent.is_empty() {
                                        ui.add(egui::Label::new(muted(parent).small()).truncate());
                                    }
                                });
                                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                                    if ui
                                        .add(egui::Button::new("✖").frame(false))
                                        .on_hover_text("Retirer de la liste")
                                        .clicked()
                                    {
                                        to_remove = Some(i);
                                    }
                                });
                            });
                        });
                }
            });

        if let Some(i) = to_remove {
            self.config.folders.remove(i);
            save_config(&self.config);
        }
    }

    fn ui_journal(&mut self, ui: &mut egui::Ui) {
        if self.log.is_empty() {
            ui.add_space(60.0);
            ui.vertical_centered(|ui| {
                ui.label(RichText::new("📜").size(44.0));
                ui.label(muted("Aucune activité pour le moment"));
            });
            return;
        }
        egui::ScrollArea::vertical()
            .auto_shrink([false, false])
            .stick_to_bottom(true)
            .show(ui, |ui| {
                ui.add(egui::Label::new(RichText::new(&self.log).monospace()));
            });
    }
}

impl eframe::App for BackupApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.drain_worker();

        // Drag & drop de dossiers
        let dropped: Vec<PathBuf> = ctx.input(|i| {
            i.raw
                .dropped_files
                .iter()
                .filter_map(|f| f.path.clone())
                .collect()
        });
        for p in dropped {
            if p.is_dir() {
                self.add_folder(p.to_string_lossy().to_string());
                self.tab = Tab::Folders;
            }
        }

        egui::SidePanel::left("side")
            .exact_width(280.0)
            .resizable(false)
            .frame(
                egui::Frame::none()
                    .fill(SIDE)
                    .stroke(Stroke::new(1.0_f32, BORDER))
                    .inner_margin(16.0),
            )
            .show(ctx, |ui| self.ui_side(ui));

        egui::CentralPanel::default()
            .frame(
                egui::Frame::none()
                    .fill(BG)
                    .inner_margin(egui::Margin::symmetric(20.0, 16.0)),
            )
            .show(ctx, |ui| self.ui_main(ui));

        // Overlay pendant un glisser-déposer
        if ctx.input(|i| !i.raw.hovered_files.is_empty()) {
            let rect = ctx.screen_rect();
            let painter = ctx.layer_painter(egui::LayerId::new(
                egui::Order::Foreground,
                egui::Id::new("drop_overlay"),
            ));
            painter.rect_filled(rect, 0.0, Color32::from_black_alpha(190));
            painter.text(
                rect.center(),
                egui::Align2::CENTER_CENTER,
                "📥  Déposez les dossiers ici",
                FontId::proportional(26.0),
                Color32::WHITE,
            );
        }

        ctx.request_repaint_after(std::time::Duration::from_millis(100));
    }
}

// ════════════════════════════════════════════════════════════════════════════════
// Utils fichiers / système
// ════════════════════════════════════════════════════════════════════════════════

fn app_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default())
}

fn config_path() -> PathBuf {
    app_dir().join(CONFIG_FILE)
}

fn load_config() -> Config {
    std::fs::read_to_string(config_path())
        .ok()
        .and_then(|s| serde_json::from_str::<Config>(&s).ok())
        .unwrap_or_default()
}

fn save_config(config: &Config) {
    if let Ok(json) = serde_json::to_string_pretty(config) {
        let _ = std::fs::write(config_path(), json);
    }
}

/// Résolution de NanaZipC : PATH, puis %LOCALAPPDATA%\Microsoft\WindowsApps\NanaZipC.exe
fn nanazip_path() -> Option<PathBuf> {
    if std::process::Command::new("NanaZipC")
        .arg("--help")
        .output()
        .is_ok()
    {
        return Some(PathBuf::from("NanaZipC"));
    }
    let local = std::env::var("LOCALAPPDATA").unwrap_or_default();
    let p = Path::new(&local)
        .join("Microsoft")
        .join("WindowsApps")
        .join("NanaZipC.exe");
    if p.is_file() {
        Some(p)
    } else {
        None
    }
}

/// Équivalent de os.path.splitdrive sur Windows ("C:\foo" -> ("C", "\foo")).
fn splitdrive(path: &Path) -> (String, PathBuf) {
    let s = path.to_string_lossy();
    let bytes = s.as_bytes();
    if bytes.len() >= 2 && bytes[1] == b':' {
        (s[..1].to_string(), PathBuf::from(&s[2..]))
    } else {
        (String::new(), path.to_path_buf())
    }
}

/// Supprime un arbre de répertoires en forçant l'écriture sur les fichiers read-only
/// (équivalent de _force_rmtree du Python, utile pour les dossiers contenant .git).
fn force_rmtree(path: &Path) {
    if !path.exists() {
        return;
    }
    let mut entries: Vec<_> = WalkDir::new(path)
        .into_iter()
        .filter_map(|e| e.ok())
        .collect();
    entries.sort_by(|a, b| b.depth().cmp(&a.depth()));
    for entry in entries {
        let p = entry.path();
        if p.is_dir() {
            let _ = std::fs::remove_dir(p);
        } else if let Err(e) = std::fs::remove_file(p) {
            if e.kind() == std::io::ErrorKind::PermissionDenied {
                if let Ok(metadata) = std::fs::metadata(p) {
                    let mut perms = metadata.permissions();
                    perms.set_readonly(false);
                    let _ = std::fs::set_permissions(p, perms);
                }
                let _ = std::fs::remove_file(p);
            }
        }
    }
    let _ = std::fs::remove_dir(path);
}

/// Copie un arbre en ignorant les dossiers .git et les fichiers verrouillés/disparus.
fn copy_tree(src: &Path, dst: &Path) -> std::io::Result<()> {
    for entry in WalkDir::new(src).into_iter().filter_map(|e| e.ok()) {
        let rel = entry.path().strip_prefix(src).unwrap();
        if rel.components().any(|c| c.as_os_str() == ".git") {
            continue;
        }
        let target = dst.join(rel);
        if entry.file_type().is_dir() {
            std::fs::create_dir_all(&target)?;
        } else {
            if let Some(parent) = target.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            let _ = std::fs::copy(entry.path(), &target); // silencieux si absent/verrouillé
        }
    }
    Ok(())
}

/// Déplace un fichier de façon sûre, même entre deux lecteurs différents.
/// `std::fs::rename` échoue avec `os error 17` (ERROR_NOT_SAME_DEVICE) sur Windows
/// quand la source et la destination sont sur des disques différents.
fn move_file(src: &Path, dst: &Path) -> std::io::Result<()> {
    if std::fs::rename(src, dst).is_ok() {
        return Ok(());
    }
    // Inter-disque : copie puis suppression de la source.
    std::fs::copy(src, dst)?;
    std::fs::remove_file(src)?;
    Ok(())
}

fn build_archive_name() -> String {
    let username = std::env::var("USERNAME").unwrap_or_else(|_| "utilisateur".into());
    let today = Local::now().format("%Y-%m-%d").to_string();
    format!("Backup-{username}_{today}.7z")
}

// ════════════════════════════════════════════════════════════════════════════════
// Cœur du backup (partagé GUI et mode -auto)
// ════════════════════════════════════════════════════════════════════════════════

fn run_backup_core<F1, F2, F3>(
    folders: &[String],
    temp_dir: &Path,
    dest_path: &Path,
    compression: i32,
    mut on_status: F1,
    mut on_progress: F2,
    mut on_log: F3,
) -> Result<(), String>
where
    F1: FnMut(&str),
    F2: FnMut(f64),
    F3: FnMut(&str),
{
    on_log("Préparation du dossier temporaire…");
    force_rmtree(temp_dir);
    std::fs::create_dir_all(temp_dir).map_err(|e| e.to_string())?;

    let valid_folders: Vec<&String> = folders.iter().filter(|f| Path::new(f).is_dir()).collect();
    if valid_folders.is_empty() {
        return Err("Aucun dossier valide à sauvegarder.".into());
    }

    // --- Copie des fichiers ---
    on_status("Copie des fichiers…");
    for (i, folder) in valid_folders.iter().enumerate() {
        let path = Path::new(folder);
        let (drive, tail) = splitdrive(path);
        let tail_str = tail.to_string_lossy();
        let tail_no_sep: &str = tail_str.strip_prefix('\\').unwrap_or(&tail_str);
        let dest_sub = temp_dir.join(&drive).join(Path::new(tail_no_sep));
        on_status(&format!(
            "Copie de {}… ({}/{})",
            path.file_name().unwrap_or_default().to_string_lossy(),
            i + 1,
            valid_folders.len()
        ));
        on_log(&format!("  Copie : {folder}"));
        copy_tree(path, &dest_sub).map_err(|e| e.to_string())?;
        on_progress(60.0 * (i + 1) as f64 / valid_folders.len() as f64);
    }

    // --- Compression NanaZip ---
    on_status("Compression en cours…");
    on_log(&format!("  Compression (niveau {compression})…"));
    let archive_tmp = temp_dir.with_extension("7z"); // temp_dir + ".7z"
    // Une archive résiduelle (run précédent échoué) fait échouer 7z : "Cannot open the file as [7z] archive".
    let _ = std::fs::remove_file(&archive_tmp);
    let use_mmax = compression == -1;
    let nanazip = nanazip_path()
        .ok_or_else(|| "NanaZip introuvable. Installez-le depuis le Microsoft Store.".to_string())?;
    let mut cmd = Command::new(nanazip);
    cmd.arg("a")
        .arg("-t7z")
        .arg(&archive_tmp)
        .arg("-r")
        .arg(temp_dir);
    if use_mmax {
        cmd.arg("-mmax");
    } else {
        cmd.arg(format!("-mx={compression}"));
    }
    cmd.arg("-bsp1");

    let mut child = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Impossible de lancer NanaZip : {e}"))?;

    let stdout = child.stdout.take().ok_or("Pas de stdout NanaZip")?;
    use std::io::{BufRead, BufReader};
    let reader = BufReader::new(stdout);
    let mut last_pct = -1i32;
    for line in reader.lines().flatten() {
        if let Some(pct_str) = line.trim().strip_suffix('%') {
            if let Ok(pct) = pct_str.trim().parse::<i32>() {
                if pct != last_pct {
                    last_pct = pct;
                    on_progress(60.0 + 35.0 * pct as f64 / 100.0);
                }
            }
        }
    }
    let output = child.wait_with_output().map_err(|e| e.to_string())?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        let _ = std::fs::remove_file(&archive_tmp);
        on_log(&format!("  ERREUR NanaZip : {stderr}"));
        return Err(format!("Erreur lors de la compression :\n{stderr}"));
    }
    on_progress(95.0);
    on_log("  Compression terminée.");

    // --- Déplacement de l'archive (sécurisé inter-disque) ---
    on_status("Déplacement de l'archive…");
    on_log(&format!("  Déplacement vers {}", dest_path.display()));
    move_file(&archive_tmp, dest_path).map_err(|e| e.to_string())?;
    on_progress(100.0);
    on_log("✅ Backup terminé avec succès !");
    Ok(())
}

// ════════════════════════════════════════════════════════════════════════════════
// Mode console (-auto)
// ════════════════════════════════════════════════════════════════════════════════

fn run_auto() {
    let config = load_config();
    let backup_dir = PathBuf::from(&config.backup_dir);
    if !backup_dir.is_dir() {
        eprintln!("Dossier de destination invalide.");
        std::process::exit(1);
    }
    if config.folders.is_empty() {
        eprintln!("Aucun dossier à sauvegarder.");
        std::process::exit(1);
    }

    let compression = COMPRESSION_LEVELS
        .iter()
        .find(|(label, _)| *label == config.compression)
        .map(|(_, level)| *level)
        .unwrap_or(5);

    let dest_path = backup_dir.join(build_archive_name());
    if dest_path.exists() {
        println!("Un backup a déjà été effectué aujourd'hui.");
        std::process::exit(0);
    }

    let temp_dir = std::env::temp_dir()
        .join(".Backup")
        .join(build_archive_name().replace(".7z", ""));

    let result = run_backup_core(
        &config.folders,
        &temp_dir,
        &dest_path,
        compression,
        |s| println!("{s}"),
        |_p| {},
        |s| println!("{s}"),
    );
    force_rmtree(&temp_dir);
    match result {
        Ok(()) => println!("Backup terminé : {}", dest_path.display()),
        Err(e) => {
            eprintln!("Erreur : {e}");
            std::process::exit(1);
        }
    }
}

// ════════════════════════════════════════════════════════════════════════════════
// Entrée
// ════════════════════════════════════════════════════════════════════════════════

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() > 1 && args[1] == "-auto" {
        run_auto();
        return;
    }

    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title(format!("{} v{}", APP_NAME, APP_VERSION))
            .with_inner_size([940.0, 620.0])
            .with_min_inner_size([780.0, 480.0])
            .with_drag_and_drop(true)
            .with_icon(
                eframe::icon_data::from_png_bytes(include_bytes!("../assets/logo.png"))
                    .expect("assets/logo.png invalide"),
            )
            .with_resizable(true),
        ..Default::default()
    };

    let _ = eframe::run_native(
        APP_NAME,
        native_options,
        Box::new(|cc| {
            cc.egui_ctx.set_theme(egui::Theme::Dark);
            Ok(Box::new(BackupApp::new(cc)))
        }),
    );
}