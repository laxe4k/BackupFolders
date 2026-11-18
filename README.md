# BackupFolders

Outil de sauvegarde avec interface graphique (Rust + egui). Copie vos dossiers et les compresse dans une archive `.7z` via 7-Zip / NanaZip.

[![GitHub Release](https://img.shields.io/github/v/release/laxe4k/BackupFolders)](https://github.com/laxe4k/BackupFolders/releases/latest)
[![Build](https://img.shields.io/github/actions/workflow/status/laxe4k/BackupFolders/build.yml?label=build)](https://github.com/laxe4k/BackupFolders/actions/workflows/build.yml)
[![Platform](https://img.shields.io/badge/platform-Windows%20|%20Linux%20|%20macOS-lightgrey)](https://github.com/laxe4k/BackupFolders/releases)
[![GitHub License](https://img.shields.io/github/license/laxe4k/BackupFolders)](LICENSE)

## Fonctionnalités

- **Interface graphique moderne** (egui, thème sombre) — sélection des dossiers et du niveau de compression, sans ligne de commande
- **Compression 7z** — niveaux de 0 (aucune) à 9 (ultra), via 7-Zip ou NanaZip
- **Glisser-déposer** de dossiers directement dans la fenêtre
- **Journal d'activité** et barre de progression en temps réel
- **Configuration persistante** (`backup_config.json`) — destination, dossiers et compression mémorisés
- **Mode automatique** (`-auto`) — backup silencieux pour le Planificateur de tâches Windows
- **Multiplateforme** — Windows, Linux et macOS (binaires compilés par GitHub Actions)
- **Exécutable standalone** — aucune dépendance Python ni runtime à installer

## Installation

### Binaires précompilés (recommandé)

Télécharger l'archive de la [dernière release](https://github.com/laxe4k/BackupFolders/releases/latest) pour votre plateforme :

- Windows : `backupfolders-windows-x64.zip` → `BackupFolders.exe`
- Linux : `backupfolders-linux-x64.tar.gz`
- macOS : `backupfolders-macos-*.tar.gz`

Extraire l'archive et lancer l'exécutable. Sur Windows, l'icône de l'application est intégrée (`assets/logo.ico`).

### Depuis les sources

```bash
git clone https://github.com/laxe4k/BackupFolders.git
cd BackupFolders
cargo build --release
```

L'exécutable se trouve dans `target/release/backupfolders` (`backupfolders.exe` sur Windows).

## Utilisation

### Interface graphique

1. Lancer `BackupFolders` (ou `BackupFolders.exe`)
2. Choisir le **dossier de destination** des backups
3. **Ajouter** les dossiers à sauvegarder (bouton ➕ ou glisser-déposer)
4. Choisir le **niveau de compression**
5. Cliquer sur **Lancer le backup**

L'archive est nommée `Backup-<utilisateur>_<date>.7z` (ex. `Backup-laxe4k_2026-11-18.7z`) et une seule peut être créée par jour.

### Mode automatique

```bash
BackupFolders.exe -auto
```

Lance le backup silencieusement avec la configuration sauvegardée. Idéal pour le **Planificateur de tâches Windows**. Code de sortie : `0` en cas de succès, `1` en cas d'erreur.

## Configuration

La configuration est enregistrée automatiquement dans `backup_config.json` :

- **Windows** : à côté de l'exécutable
- **Linux** : `~/.config/BackupFolders/backup_config.json`
- **macOS** : `~/Library/Application Support/BackupFolders/backup_config.json`

Elle contient le dossier de destination, la liste des dossiers à sauvegarder et le niveau de compression choisi.

## Niveaux de compression

| Libellé | `-mx` | Description |
|---------|-------|-------------|
| 0 - Aucune | 0 | Archivage sans compression |
| 1 - Le plus rapide | 1 | Compression rapide, faible taux |
| 3 - Rapide | 3 | |
| 5 - Normale | 5 | Équilibre vitesse / taux (par défaut) |
| 7 - Maximum | 7 | |
| 9 - Ultra | 9 | Compression maximale, plus lent |

## Prérequis

Une implémentation de 7-Zip doit être disponible sur le système :

- **Windows** : [NanaZip](https://github.com/M2Team/NanaZip) (Microsoft Store) ou [7-Zip](https://www.7-zip.org/) (`7z` / `7zz` dans le `PATH`, ou `NanaZipC.exe` dans `WindowsApps`)
- **Linux** : `sudo apt install p7zip-full` (fournit `7zz`)
- **macOS** : `brew install sevenzip` (`7zz` dans `/opt/homebrew/bin` ou `/usr/local/bin`)

Si aucun exécutable 7z n'est trouvé, le backup échoue avec un message explicite.

## Notes techniques

- Les dossiers `.git` sont exclus de la copie.
- Les fichiers verrouillés ou disparus sont ignorés silencieusement lors de la copie.
- L'archive est d'abord créée dans un dossier temporaire, puis déplacée vers la destination (fonctionne même entre deux lecteurs différents).
- Sur Windows, l'application s'ouvre en fenêtre (pas de console clignotante) grâce à `windows_subsystem = "windows"`.

## Licence

[MIT](LICENSE) © 2025 Laxe4k