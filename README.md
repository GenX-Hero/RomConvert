# RomConvert

A Bash script designed to streamline and automate ROM extraction, conversion, and compression for emulation frontends (such as ES-DE and RetroArch). It automatically extracts multi-format archives and converts disc images into highly compressed `.chd` or `.cso` formats.

---

## Features

- **Multi-Format Extraction**: Handles `.zip`, `.7z`, and RAR5/legacy `.rar` archives (including non-UTF8 filenames) using `unar`, `7z`, and `unzip`.
- **CHD Compression**: Converts PS1 and PS2 disc images (`.cue`/`.bin`, `.iso`) to `.chd` using `chdman`.
- **CSO Compression**: Compresses PSP `.iso` files to `.cso` using multi-threaded `maxcso`.
- **Multi-Disc Support**: Automatically generates `.m3u` playlist files for multi-disc titles.
- **Clean Workspace**: Automatically purges temporary extracted files post-conversion to save disk space.

---

## Prerequisites & Dependencies

The script relies on CLI utilities to extract archives, process CUE files, and compress disc images.

### Installation & Dependencies

#### Debian / Ubuntu

```bash
# 1. Install system tools & build dependencies
sudo apt update
sudo apt install -y mame-tools p7zip-full unar unzip build-essential git libuv1-dev liblz4-dev zlib1g-dev libdeflate-dev

# 2. Build and install maxcso
cd /tmp
git clone https://github.com/unknownbrackets/maxcso.git
cd maxcso
make LDFLAGS="-luv -lpthread" && sudo make install
cd /tmp && rm -rf /tmp/maxcso
```

#### RHEL / AlmaLinux / Rocky Linux 9

```bash
# 1. Enable EPEL & CRB repositories
sudo dnf install -y epel-release
sudo crb enable

# 2. Install runtime dependencies & build tools
sudo dnf install -y p7zip p7zip-plugins unar unzip cpio gcc-c++ make git libuv-devel lz4-devel zlib-devel libdeflate-devel

# 3. Extract chdman standalone binary
cd /tmp
wget -O mame-tools.rpm https://kojipkgs.fedoraproject.org/packages/mame/0.269/1.fc41/x86_64/mame-tools-0.269-1.fc41.x86_64.rpm
rpm2cpio mame-tools.rpm | cpio -idmv ./usr/bin/chdman
sudo mv usr/bin/chdman /usr/local/bin/
rm -f /tmp/mame-tools.rpm

# 4. Build and install maxcso
cd /tmp
git clone https://github.com/unknownbrackets/maxcso.git
cd maxcso
make && sudo make install
cd /tmp && rm -rf /tmp/maxcso
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
