# RomConvert

A Bash script designed to streamline and automate ROM extraction, conversion, and compression for emulation frontends (such as ES-DE and RetroArch). It automatically extracts multi-format archives and converts disc images into highly compressed `.chd` or `.cso` formats.

---

## Features

- **Multi-Format Extraction**: Handles `.zip`, `.7z`, and RAR5/legacy `.rar` archives (including non-UTF8 filenames) using `unar`, `7z`, and `unzip`.
- **CHD Compression**: Converts PS1, PS2, and PSP disc images (`.cue`/`.bin`, `.iso`) to `.chd` using `chdman`.
- **CSO Compression**: Compresses PSP `.iso` files to `.cso` using multi-threaded `maxcso`.
- **Multi-Disc Support**: Automatically generates `.m3u` playlist files for multi-disc titles.
- **Clean Workspace**: Automatically purges temporary extracted files post-conversion to save disk space.

---

## Prerequisites & Dependencies

The script relies on CLI utilities to extract archives, process CUE files, and compress disc images.

### Debian / Ubuntu / WSL

1. Install base dependencies via `apt`:

```bash
sudo apt update && sudo apt install -y mame-tools p7zip-full p7zip-rar unzip unar
```

2. Install `maxcso` (download binary directly if not available in your distribution's APT repositories, e.g., Ubuntu 24.04+):

```bash
wget [https://github.com/UnknownBrackets/maxcso/releases/download/v1.13.0/maxcso](https://github.com/UnknownBrackets/maxcso/releases/download/v1.13.0/maxcso)
chmod +x maxcso
sudo mv maxcso /usr/local/bin/
```


#### Fedora / RHEL / Rocky Linux / AlmaLinux

> **Note for RHEL / AlmaLinux / Rocky Linux 9:** Enable EPEL, CRB, and RPM Fusion repositories first.

```bash
# Enable EPEL & CRB (RHEL / Alma / Rocky 9)
sudo dnf install -y epel-release
sudo crb enable

# Enable RPM Fusion (required for mame-tools on EL9)
sudo dnf install -y https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-9.noarch.rpm https://mirrors.rpmfusion.org/nonfree/el/rpmfusion-nonfree-release-9.noarch.rpm

# Install dependencies
sudo dnf install -y mame-tools p7zip p7zip-plugins unar unzip
```

---

## Dependency Breakdown

| Binary | Package (Debian/Ubuntu) | Package (RHEL/Fedora) | Purpose |
| :--- | :--- | :--- | :--- |
| `chdman` | `mame-tools` | `mame-tools` | Converts CD/DVD disc images (`.cue`, `.iso`) to `.chd` |
| `maxcso` | Direct Binary / `maxcso` | `maxcso` | Multi-threaded compression for PSP `.iso` to `.cso` |
| `7z` | `p7zip-full` / `p7zip-rar` | `p7zip` / `p7zip-plugins` | Extracts `.7z`, `.zip`, and standard archives |
| `unar` | `unar` | `unar` | Robust extraction for RAR5 and non-UTF8 encoded archives |
| `unzip` | `unzip` | `unzip` | Fast extraction for standard `.zip` files |

---

## Verification

To verify that all required dependencies are correctly installed and available in your `$PATH`:

```bash
which chdman maxcso 7z unar unzip
```

---

## Usage

1. Grant execution permissions to the script:
   ```bash
   chmod +x romconvert.sh
   ```

2. Run the script by specifying your target ROM directory:
   ```bash
   ./romconvert.sh /path/to/roms
   ```
