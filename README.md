<img width="1024" height="572" alt="image" src="https://github.com/user-attachments/assets/9b6cdc1a-0a6b-4daf-b4af-06d6172e8f52" />


# 🔄 RomConvert

A Bash script designed to streamline and automate ROM extraction, conversion, and compression for emulation frontends (such as ES-DE and RetroArch). It automatically extracts multi-format archives and converts disc images into highly compressed `.chd` or `.cso` formats.

---

## 🚀 Features

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
sudo apt install -y p7zip-full unar unzip build-essential git libuv1-dev liblz4-dev zlib1g-dev libdeflate-dev libutf8proc3

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
sudo dnf install 7zip unar unzip cpio SDL3 flac-libs utf8proc

# 2. Download, extract, and add chdman to PATH (saving gigabytes of unnecessary MAME dependencies)
sudo dnf download mame-tools
mkdir -p ~/.local/bin
mv ./usr/bin/chdman ~/.local/bin/
rm -rf ./usr ./etc ./usr/share mame-tools-*.rpm

# 3. Install maxcso
dnf copr enable phantomx/chinforpms
sudo dnf install maxcso
```

### 🏠 2. Install RomConvert (Local Setup)

Clone the repository and create a symbolic link to your local user's binary directory:

```bash
git clone https://github.com/GenX-Hero/RomConvert.git
cd RomConvert
mkdir -p ~/.local/bin
ln -s $(pwd)/romconvert.sh ~/.local/bin/romconvert
```

---

### ⚙️ Dependency Breakdown

| Binary | Package (Debian/Ubuntu) | Package (Fedora) | Purpose |
| :--- | :--- | :--- | :--- |
| `chdman` | `mame-tools` *(extracted)* | `mame-tools` *(extracted)* | Converts CD/DVD disc images (`.cue`, `.iso`) to `.chd` |
| `maxcso` | Custom Build | `maxcso` *(via COPR)* | Multi-threaded compression for PSP `.iso` to `.cso` |
| `7z` | `p7zip-full` | `7zip` | Extracts `.7z`, `.zip`, and standard archives |
| `unar` | `unar` | `unar` | Robust extraction for RAR5 and non-UTF8 encoded archives |
| `unzip` | `unzip` | `unzip` | Fast extraction for standard `.zip` files |

---

### 🔍 Verification

To verify that all required dependencies are correctly installed and available in your `$PATH`:

```bash
which chdman maxcso 7z unar unzip
```

---

## ⚙️ Customization & Configuration

Before running the script, open `romconvert.sh` in a text editor to verify or adapt the path configuration to your personal setup.

### 📂 Target Directory Variables
By default, the script points directly to the default **EmulationStation Desktop Edition (ES-DE)** ROM directories. Edit these paths in `romconvert.sh` if your setup differs:

```bash
# Path definitions inside romconvert.sh
DEST_DIR="/mnt/d/ES-DE/ROMs"
CUE_DIR="/mnt/d/RomConvert/CUE_Library/PSX"
```

> ⚠️ **Note**: As distributed, these variables reflect the author's specific ES-DE installation paths. Modify them at your own risk to match your local storage structure or mount points.

### 📑 CUE File Library (`CUE_DIR`)
For PS1 conversion, if an archive contains orphaned or corrupted `.bin` files missing their corresponding `.cue` sheet, `RomConvert` checks `CUE_DIR` for standard Redump `.cue` files to automatically recover and rebuild the disc structure before converting to `.chd`.

---

## 📀 Multi-Disc Handling & Folder Structure

For multi-disc PS1 games, `RomConvert` relies on standard **Redump naming conventions** to group discs correctly.

### 🏷️ Disc Tag Requirement
Source archive filenames **must include disc tag indicators** such as `(Disc 1)`, `(Disc 2)`, `(Disc 3)` (or `(Disc A)`, `(Disc B)`, etc.).

* **Correct Multi-Disc Naming**:
  * `Final Fantasy VII (USA) (Disc 1).7z`
  * `Final Fantasy VII (USA) (Disc 2).7z`
  * `Final Fantasy VII (USA) (Disc 3).7z`

> ⚠️ **Important**: If disc tags like `(Disc 1)` are missing from the source filenames, the script will treat each archive as an independent single-disc title and process them separately.

### 📁 `.multidisc` Directory Logic
When a multi-disc set is processed:
1. A hidden directory named `.multidisc/<Game Name>` is created inside the target folder.
2. Individual `.chd` files for each disc are placed inside `.multidisc/<Game Name>/`.
3. A single `.m3u` playlist referencing all discs is generated in the root PS1 directory, ensuring frontends like ES-DE show a clean, single game entry instead of multiple disc entries.

💡 Tip: In ES-DE, place the .multidisc folder inside the psx ROMs directory at the same level as the .m3u playlist and single-disc .chd files. Ensure "Show Hidden Files/Folders" is toggled OFF in ES-DE settings for a clean game list.

---

## 💻 Usage

Run the script by specifying the target system and the archive file(s) or pattern to process:

```bash
romconvert <system> <archive_file_or_pattern>
```

### 🎮 Supported Systems
* `psx` – Converts PS1 archives (`.zip`, `.7z`, `.rar`) to `.chd` using `chdman`. Generates `.m3u` for multi-disc titles.
* `ps2` – Converts PS2 archives (`.zip`, `.7z`, `.rar`) to `.chd` using `chdman`.
* `psp` – Converts PSP archives (`.zip`, `.7z`, `.rar`) to `.cso` using `maxcso`.

### 💡 Examples

```bash
# Convert single-disc PS1 games
romconvert psx "Tomb Raider*.7z"

# Convert a multi-disc PS1 game (archive names must include (Disc 1), (Disc 2), etc.)
romconvert psx "Final Fantasy VII*.7z"

# Convert PS2 archives
romconvert ps2 "Metal Gear Solid 2*.zip"

# Convert a PSP game
romconvert psp "Wild Arms XF*.7z"

# Convert a batch of single disc games (keep this within the same system)
# Assuming you have in the folder: both "God of Wars (NTSC).7z" and "God of Wars II (PAL).zip"
romconvert ps2 "God of Wars*"


```
