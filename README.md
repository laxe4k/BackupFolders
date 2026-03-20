# BackupFolders

Outil de sauvegarde Windows avec interface graphique. Compresse vos dossiers en archive `.7z` via 7-Zip.

[![GitHub Release](https://img.shields.io/github/v/release/laxe4k/BackupFolders)](https://github.com/laxe4k/BackupFolders/releases/latest)
![Python](https://img.shields.io/badge/python-3.10+-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
[![GitHub License](https://img.shields.io/github/license/laxe4k/BackupFolders)](LICENSE)

## Fonctionnalités

- **Interface graphique** — sélection des dossiers et du niveau de compression sans ligne de commande
- **Compression 7z** — niveaux de 0 (stockage) à 9 (maximum)
- **Configuration persistante** — sauvegardée automatiquement dans `backup_config.json`
- **Installation automatique de 7-Zip** via winget si absent
- **Mode automatique** (`-auto`) — pour le Planificateur de tâches Windows
- **Exécutable standalone** — compilable en `.exe` sans dépendance Python

## Installation

### Exécutable Windows (recommandé)

Télécharger `BackupFolders.exe` depuis la [dernière release](https://github.com/laxe4k/BackupFolders/releases/latest).

### Depuis les sources

```bash
git clone https://github.com/laxe4k/BackupFolders.git
cd BackupFolders
python BackupFolders.py
```

## Utilisation

### Interface graphique

1. Lancer `BackupFolders.py` ou `BackupFolders.exe`
2. Définir le **dossier de destination** des backups
3. **Ajouter** les dossiers à sauvegarder
4. Choisir le **niveau de compression**
5. Cliquer sur **Lancer le backup**

L'archive générée sera nommée `Backup-<utilisateur>_<date>.7z`.

### Mode automatique

```bash
BackupFolders.exe -auto
```

Lance le backup silencieusement avec la configuration sauvegardée. Utile pour le Planificateur de tâches Windows.

## Prérequis

- **Python 3.10+** (pour exécuter depuis les sources)
- **7-Zip** (installé automatiquement si absent)