<img width="1024" height="572" alt="image" src="https://github.com/user-attachments/assets/9b6cdc1a-0a6b-4daf-b4af-06d6172e8f52" />


# 🔄 RomConvert 2.0

A Python application designed to streamline and automate ROM extraction, conversion, and compression for emulation frontends (such as ES-DE and RetroArch). It automatically extracts multi-format archives and converts disc images into highly compressed `.chd` or `.cso` formats.

---

## 🚀 Features

* 🖥️ **Interactive TUI**: Built with Textual for a modern terminal dashboard with real-time status and log monitoring.
* 🔍 **Pre-Flight Inspection**: Automatically checks staging files for structural anomalies, missing `.cue` files, and mandatory `.sbi` requirements before conversion.
* 🗄️ **REDUMP Database Integration**: Uses a local SQLite database populated from REDUMP DATs to identify LibCrypt-protected PSX titles and enforce `.sbi` presence.
* 📦 **Multi-Format Extraction**: Handles `.zip`, `.7z`, and RAR5/legacy `.rar` archives (including non-UTF8 filenames) using `unar`, `7z`, and `unzip`.
* 💿 **CHD Compression**: Converts PS1 and PS2 disc images (`.cue` / `.bin`, `.iso`) to `.chd` using `chdman`.
* 🗜️ **CSO Compression**: Compresses PSP `.iso` files to `.cso` using multi-threaded `maxcso`.
* 📀 **Multi-Disc Support**: Automatically generates `.m3u` playlist files for multi-disc titles.
* 🧹 **Clean Workspace**: Automatically purges temporary extracted files post-conversion to save disk space.

---

## 🛠️ Prerequisites & Dependencies

The script relies on CLI utilities to extract archives, process CUE files, and compress disc images.

### 📥 1. Install System Dependencies

#### <img valign="middle" width="16" height="16" alt="Windows Users" src="https://github.com/user-attachments/assets/bf925b76-ff9d-4054-8639-27084c7289dd" /> Windows Users

```powershell
# Windows users must install and run a WSL2 Linux distribution. (Tested and fully working on Fedora,
# Debian, and Ubuntu; major dependency issues were encountered on AlmaLinux, Rocky Linux, and other
# RHEL-based enterprise distributions).

# View all available Linux distributions
wsl --list --online

# Install a distribution (e.g., Debian)
wsl --install -d Debian
```

#### <img  valign="middle" width="16" height="16" alt="Debian Users" src="https://github.com/user-attachments/assets/1cfa396c-de6a-4ee9-b8db-7e482936abfa" /> Debian / <img  valign="middle" width="16" height="16" alt="Ubuntu Users" src="https://github.com/user-attachments/assets/e41b571e-5926-4a25-a3e1-52e6ff6d7714" /> Ubuntu Users

```bash
# 1. Install system tools & build dependencies
sudo apt update
sudo apt install -y build-essential git make zip unzip unar p7zip-full libsdl2-dev zlib1g-dev libbz2-dev libuv1-dev liblz4-dev libdeflate-dev libutf8proc-dev

# 2. Download, extract, and add chdman to PATH (saving gigabytes of unnecessary MAME dependencies)
cd /tmp
apt-get download mame-tools
dpkg-deb -x mame-tools_*.deb ./mame-extracted
mkdir -p ~/.local/bin
mv ./mame-extracted/usr/bin/chdman ~/.local/bin/
rm -rf /tmp/mame-tools_*.deb /tmp/mame-extracted

# 3. Build and install maxcso
cd /tmp
git clone [https://github.com/unknownbrackets/maxcso.git](https://github.com/unknownbrackets/maxcso.git)
cd maxcso
make LDFLAGS="-luv -lpthread" && sudo make install
cd /tmp && rm -rf /tmp/maxcso
```

#### <img  valign="middle" width="20" height="20" alt="Fedora Users" src="https://github.com/user-attachments/assets/51f82c2e-a8ef-4e6d-8df4-236ba474fe61" /> Fedora Users

```bash
# 1. Install system tools & build dependencies
sudo dnf install -y gcc gcc-c++ libstdc++-static make git zip unzip 7zip unar cpio SDL2-devel zlib-devel bzip2-devel libuv-devel lz4-devel libdeflate-devel utf8proc-devel

# 2. Download, extract, and add chdman to PATH (saving gigabytes of unnecessary MAME dependencies)
sudo dnf download mame-tools
mkdir -p ~/.local/bin
mv ./usr/bin/chdman ~/.local/bin/
rm -rf ./usr ./etc ./usr/share mame-tools-*.rpm

# 3. Install maxcso
dnf copr enable phantomx/chinforpms
sudo dnf install maxcso
```

---

### 🔍 2. Verification

To verify that all required dependencies are correctly installed and available in your `$PATH`:

```bash
which chdman maxcso 7z unar unzip
```

---

#### ⚙️ Dependency Breakdown

| Binary | Package (Debian/Ubuntu) | Package (Fedora) | Purpose |
| :--- | :--- | :--- | :--- |
| `chdman` | `mame-tools` *(extracted)* | `mame-tools` *(extracted)* | Converts CD/DVD disc images (`.cue`, `.iso`) to `.chd` |
| `maxcso` | Custom Build | `maxcso` *(via COPR)* | Multi-threaded compression for PSP `.iso` to `.cso` |
| `7z` | `p7zip-full` | `7zip` | Extracts `.7z`, `.zip`, and standard archives |
| `unar` | `unar` | `unar` | Robust extraction for RAR5 and non-UTF8 encoded archives |
| `unzip` | `unzip` | `unzip` | Fast extraction for standard `.zip` files |

---

### 🏠 3. Install RomConvert (Local Setup)

Clone the repository, set up the Python virtual environment, and run the application:

```bash
# 1. Clone the repository
git clone https://github.com/GenX-Hero/RomConvert.git
cd RomConvert

# 2. Create python virtual env and install required packages
python3 -m venv venv
source venv/bin/activate
pip install textual py7zr rarfile

# 3. Make executable and launch the tool
chmod +x RomConvert.py
./RomConvert.py

```

For running the app again in the future, remember to activate the venv with `source venv/bin/activate`.

---

## ⚙️ Customization & Configuration

The application generates a `RomConvert.CFG` configuration file automatically on its first run. 

### 📂 Workspace Directories
By default, the application uses self-contained relative directories within its own root folder. You can open `RomConvert.CFG` in any text editor and change these to your absolute paths (e.g., an external drive or a network share).

```ini
[Settings]
SOURCE_DIR = "./SOURCE/"
TARGET_DIR = "./TARGET/"
TEMPOR_DIR = "./TEMPORARY/"
REDUMP_DIR = "./REDUMP/"
STORED_DIR = "./ARCHIVE/"
REJECT_DIR = "./REJECTED/"
HIDDEN_DIR = ".multidisc"
Quick_TIME = false
```

> 💡 **Tip**: If you change `TARGET_DIR` to point directly to your emulator's ROM folder (e.g., `/mnt/d/ES-DE/ROMs/`), RomConvert will place the converted `.chd` and `.cso` files directly into your frontend's library!

---

### 📑 Redump Integration (Auto CUE & SBI Recovery)
In version 1.0, users had to manually download and manage CUE sheets. **Version 2.0 handles this entirely automatically.**

When you run RomConvert for the first time, the **Interactive Pre-Flight Checklist** will safely connect to [Redump.org](http://redump.org) to:
1. Download the latest DAT, CUE, and SBI archives.
2. Build a local SQLite database (`RomConvert.DB`) and automatically populate the `REDUMP/` directory structure.

#### 🛠️ How it works during conversion:
- **Missing CUEs**: If an archive contains orphaned or corrupted `.bin` files missing their corresponding `.cue` sheet, RomConvert queries the DB, checks the track CRC32, and seamlessly injects the correct CUE file from the `REDUMP/` cache to allow `chdman` to compress the disc image.
- **LibCrypt Protection (.sbi)**: If you convert a European (PAL) PS1 game that uses LibCrypt copy protection, RomConvert automatically detects it via the database and places the required `.sbi` file exactly where it belongs alongside your newly created `.chd`.

---

## 📀 Multi-Disc Handling & Folder Structure

For multi-disc titles, `RomConvert` leverages the official **Redump naming conventions** retrieved from the local database to group discs correctly.

### 🏷️ Redump Disc Recognition
The application identifies multi-disc sets automatically by parsing the canonical game names provided by the Redump DAT files, which natively include tags like `(Disc 1 of 2)`, `(Disc 2 of 2)`, or `(Disc 1)`.

- **Recognized Multi-Disc Structure**:
  * `Final Fantasy VII (USA) (Disc 1 of 3).7z`
  * `Final Fantasy VII (USA) (Disc 2 of 3).7z`
  * `Final Fantasy VII (USA) (Disc 3 of 3).7z`

> ⚠️ **Important**: If the source files do not match a multi-disc entry in the Redump database or lack proper identification, the script will process them as independent single-disc titles.

### 📁 `.multidisc` Directory Logic
When a multi-disc set is processed:
1. A hidden directory named `.multidisc/<Game Name>` is created inside the target system folder.
2. Individual `.chd` (or `.cso`) files for each disc are placed inside `.multidisc/<Game Name>/`.
3. A single `.m3u` playlist referencing all discs is generated in the root system directory, ensuring frontends like ES-DE show a clean, single game entry instead of multiple disc clutter.

> 💡 **Tip**: In ES-DE, place the `.multidisc` folder inside your ROMs directory at the same level as the `.m3u` playlist and single-disc files. Ensure "Show Hidden Files/Folders" is toggled **OFF** in your frontend settings for a pristine game library view.

---

## 💻 Usage

Launch the interactive Textual dashboard from within the project directory:

```bash
python3 RomConvert.py
```

### 🖥️ Workflow Overview
1. **Startup & Pre-Flight Checks**: The application automatically verifies your database, parses Redump DAT records, and checks your CUE/SBI cache files. 
   > 💡 **Tip**: If you already know your environment is fully set up and operational, you can set `Quick_TIME = true` inside `RomConvert.CFG` to skip the 1-second delay between pre-flight checklist steps and speed up startup.
2. **Scan Staging Directory**: Click **`🔍 Scan Staging Dir`** to analyze all raw or compressed ROMs placed inside your configured `SOURCE/` folder.
3. **Review Queue & Diagnostics**: Inspect the interactive table for missing files, multi-disc completion status, and validation flags (`+++`, `WRN`, `---`).
4. **Execute Conversion**: Once all items pass inspection, click **`🚀 Start Conversion`** to safely extract, compress (`.chd` / `.cso`), organize multi-disc `.m3u` playlists, copy required `.sbi` files, and archive original files.
