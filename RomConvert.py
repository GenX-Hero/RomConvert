#!/usr/bin/env python3
import os
import sqlite3
import configparser
import urllib.request
import time
import zipfile
import shutil
import re
import subprocess
import zlib
import py7zr
import rarfile
import xml.etree.ElementTree as ET
from urllib.error import URLError, HTTPError
from typing import Tuple

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, RichLog, Label, Static, Button, DataTable
from textual.containers import Vertical, Horizontal, Container
from textual.message import Message
from textual import on, work


# ==============================================================================
# DATABASE OPERATIONS
# ==============================================================================
DB_NAME = "RomConvert.DB"

def RC_Oper_DB_Check(db_path: str = DB_NAME) -> Tuple[bool, str]:
    if not os.path.exists(db_path):
        return False, "Database file missing."

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dat_entries'")
        if not cursor.fetchone():
            conn.close()
            return False, "Corrupted structure: missing 'dat_entries' table."

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta_info'")
        if not cursor.fetchone():
            conn.close()
            return False, "Corrupted structure: missing 'meta_info' table."

        cursor.execute("PRAGMA table_info(dat_entries)")
        existing_columns = [col[1] for col in cursor.fetchall()]
        required_columns = ["id", "system", "game_name", "rom_name", "size", "crc", "md5", "sha1", "has_sbi"]

        missing_columns = [req for req in required_columns if req not in existing_columns]

        if missing_columns:
            conn.close()
            return False, f"Corrupted structure: missing columns {missing_columns}."

        conn.close()
        return True, "Database is valid."
    except sqlite3.Error as e:
        return False, f"Database corruption detected (SQL error: {e})"


def RC_Oper_DB_Create(db_path: str = DB_NAME) -> Tuple[bool, str]:
    try:
        if os.path.exists(db_path):
            os.remove(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE dat_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system TEXT NOT NULL,
                game_name TEXT NOT NULL,
                rom_name TEXT NOT NULL,
                size INTEGER NOT NULL,
                crc TEXT,
                md5 TEXT,
                sha1 TEXT,
                has_sbi INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('CREATE INDEX idx_crc ON dat_entries(crc)')
        cursor.execute('CREATE INDEX idx_md5 ON dat_entries(md5)')

        cursor.execute('''
            CREATE TABLE meta_info (
                config_key TEXT PRIMARY KEY,
                config_value TEXT NOT NULL
            )
        ''')

        conn.commit()
        conn.close()
        return True, "Database successfully restored and created from scratch."
    except (sqlite3.Error, OSError) as e:
        return False, f"Database restoration failed: {e}"


def RC_Oper_DAT_Get_Stats(db_path: str = DB_NAME) -> dict:
    stats = {
        "PSX": {"records": 0, "discs": 0},
        "PS2": {"records": 0, "discs": 0},
        "PSP": {"records": 0, "discs": 0}
    }
    
    if not os.path.exists(db_path):
        return stats

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dat_entries'")
        if not cursor.fetchone():
            conn.close()
            return stats

        for sys_name in stats.keys():
            cursor.execute("SELECT COUNT(*) FROM dat_entries WHERE system = ?", (sys_name,))
            res_rec = cursor.fetchone()
            stats[sys_name]["records"] = res_rec[0] if res_rec else 0

            cursor.execute("SELECT COUNT(DISTINCT game_name) FROM dat_entries WHERE system = ?", (sys_name,))
            res_disc = cursor.fetchone()
            stats[sys_name]["discs"] = res_disc[0] if res_disc else 0

        conn.close()
    except sqlite3.Error:
        pass

    return stats


def RC_Oper_DAT_Check_Records(db_path: str = DB_NAME) -> Tuple[bool, dict]:
    stats = RC_Oper_DAT_Get_Stats(db_path)
    total_records = sum(v["records"] for v in stats.values())
    return total_records > 0, stats


def calculate_file_crc32(filepath: str) -> str:
    """Calcola il CRC32 di un file locale di grandi dimensioni a blocchi per evitare il caricamento in RAM."""
    prev = 0
    try:
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(1048576) # 1MB chunks
                if not chunk:
                    break
                prev = zlib.crc32(chunk, prev)
        return format(prev & 0xFFFFFFFF, '08x')
    except Exception:
        return ""


# ==============================================================================
# REDUMP OPERATIONS (DAT, CUE, SBI)
# ==============================================================================
REDUMP_ENDPOINTS = {
    "DAT": {
        "PSX": "http://redump.org/datfile/psx/",
        "PS2": "http://redump.org/datfile/ps2/",
        "PSP": "http://redump.org/datfile/psp/"
    },
    "CUE": {
        "PSX": "http://redump.org/cues/psx/",
        "PS2": "http://redump.org/cues/ps2/"
    },
    "SBI": {
        "PSX": "http://redump.org/sbi/psx/"
    }
}

def RC_Oper_Smart_Download(category: str, tempor_dir: str, redump_dir: str) -> dict:
    for d in [tempor_dir, redump_dir]:
        if not os.path.exists(d):
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as e:
                return {"ERROR": (False, f"Unable to create folder {d}: {e}")}

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    results = {}

    if category not in REDUMP_ENDPOINTS:
        return {"ERROR": (False, f"Invalid category: {category}.")}

    for system, url in REDUMP_ENDPOINTS[category].items():
        req = urllib.request.Request(url, headers=headers)
        
        try:
            req.method = 'HEAD'
            with urllib.request.urlopen(req, timeout=10) as response:
                remote_filename = response.info().get_filename()

            if not remote_filename:
                remote_filename = f"{system}_{category.lower()}.zip"

            final_filepath = os.path.join(redump_dir, remote_filename)

            if os.path.exists(final_filepath):
                results[system] = (True, f"Up-to-date file already present ({remote_filename})")
                continue

            temp_filepath = os.path.join(tempor_dir, remote_filename)
            req.method = 'GET'
            with urllib.request.urlopen(req, timeout=30) as response, open(temp_filepath, 'wb') as out_file:
                out_file.write(response.read())
            
            for existing_file in os.listdir(redump_dir):
                if system.lower() in existing_file.lower() and category.lower() in existing_file.lower():
                    old_path = os.path.join(redump_dir, existing_file)
                    if os.path.isfile(old_path):
                        try:
                            os.remove(old_path)
                        except OSError:
                            pass

            shutil.move(temp_filepath, final_filepath)
            results[system] = (True, f"Downloaded new file ({remote_filename})")

        except HTTPError as e:
            results[system] = (False, f"HTTP Error {e.code}")
        except URLError as e:
            results[system] = (False, f"Network error: {e.reason}")
        except Exception as e:
            results[system] = (False, f"Unexpected error: {e}")

    return results


def RC_Oper_DAT_Parse_And_Populate(db_path: str, source_dir: str) -> dict:
    SYSTEM_MAP = {
        "Sony - PlayStation": "PSX",
        "Sony - PlayStation 2": "PS2",
        "Sony - PlayStation Portable": "PSP"
    }
    
    if not os.path.exists(source_dir):
        return {"success": False, "error": f"Directory not found: {source_dir}"}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for file in os.listdir(source_dir):
            if file.lower().endswith(".zip") and "datfile" in file.lower():
                zip_path = os.path.join(source_dir, file)
                
                try:
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        dat_files = [f for f in zf.namelist() if f.lower().endswith('.dat')]
                        if not dat_files:
                            continue
                        
                        for dat_filename in dat_files:
                            with zf.open(dat_filename) as f:
                                tree = ET.parse(f)
                                root = tree.getroot()
                                
                                header = root.find('header')
                                if header is None: continue
                                name_elem = header.find('name')
                                if name_elem is None: continue
                                    
                                sys_full = name_elem.text
                                system = SYSTEM_MAP.get(sys_full, sys_full)
                                
                                cursor.execute("DELETE FROM dat_entries WHERE system = ?", (system,))
                                
                                records_to_insert = []
                                for game in root.findall('game'):
                                    game_name = game.get('name', 'Unknown')
                                    for rom in game.findall('rom'):
                                        rom_name = rom.get('name', '')
                                        size_str = rom.get('size', '0')
                                        size = int(size_str) if size_str.isdigit() else 0
                                        crc = rom.get('crc', '')
                                        md5 = rom.get('md5', '')
                                        sha1 = rom.get('sha1', '')
                                        
                                        records_to_insert.append((
                                            system, game_name, rom_name, size, crc, md5, sha1, 0
                                        ))
                                
                                if records_to_insert:
                                    cursor.executemany('''
                                        INSERT INTO dat_entries (system, game_name, rom_name, size, crc, md5, sha1, has_sbi)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    ''', records_to_insert)
                
                except zipfile.BadZipFile:
                    pass

        conn.commit()
        conn.close()
        return {"success": True, "error": None}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def RC_Oper_Update_SBI_Flags(db_path: str, redump_dir: str) -> None:
    sbi_dir = os.path.join(redump_dir, "PSX", "SBI")
    if not os.path.exists(sbi_dir):
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        sbi_files = {os.path.splitext(f)[0] for f in os.listdir(sbi_dir) if f.lower().endswith('.sbi')}

        if sbi_files:
            cursor.execute("SELECT id, game_name FROM dat_entries WHERE system = 'PSX'")
            rows = cursor.fetchall()

            for row_id, game_name in rows:
                if game_name in sbi_files:
                    cursor.execute("UPDATE dat_entries SET has_sbi = 1 WHERE id = ?", (row_id,))

            conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


# ==============================================================================
# CONFIGURATION MANAGEMENT
# ==============================================================================
CONFIG_FILE = "RomConvert.CFG"

SOURCE_DIR = "./SOURCE/"
TARGET_DIR = "./TARGET/"
TEMPOR_DIR = "./TEMPORARY/"
REDUMP_DIR = "./REDUMP/"
STORED_DIR = "./ARCHIVE/"
REJECT_DIR = "./REJECTED/"
HIDDEN_DIR = ".multidisco"
Quick_TIME = False

def RC_Oper_Config_Load(cfg_path: str = CONFIG_FILE) -> Tuple[bool, str]:
    global SOURCE_DIR, TARGET_DIR, TEMPOR_DIR, REDUMP_DIR, STORED_DIR, REJECT_DIR, HIDDEN_DIR, Quick_TIME

    config = configparser.ConfigParser()

    if not os.path.exists(cfg_path):
        try:
            config["Settings"] = {
                "SOURCE_DIR": "./SOURCE/",
                "TARGET_DIR": "./TARGET/",
                "TEMPOR_DIR": "./TEMPORARY/",
                "REDUMP_DIR": "./REDUMP/",
                "STORED_DIR": "./ARCHIVE/",
                "REJECT_DIR": "./REJECTED/",
                "HIDDEN_DIR": ".multidisco",
                "Quick_TIME": "false"
            }
            with open(cfg_path, "w") as configfile:
                config.write(configfile)
        except IOError as e:
            return False, f"Failed to create default config file: {e}"

    try:
        config.read(cfg_path)
        if not config.has_section("Settings"):
            return False, "Configuration file missing [Settings] section."

        SOURCE_DIR = config.get("Settings", "SOURCE_DIR", fallback="./SOURCE/").strip("\"'")
        TARGET_DIR = config.get("Settings", "TARGET_DIR", fallback="./TARGET/").strip("\"'")
        TEMPOR_DIR = config.get("Settings", "TEMPOR_DIR", fallback="./TEMPORARY/").strip("\"'")
        REDUMP_DIR = config.get("Settings", "REDUMP_DIR", fallback="./REDUMP/").strip("\"'")
        STORED_DIR = config.get("Settings", "STORED_DIR", fallback="./ARCHIVE/").strip("\"'")
        REJECT_DIR = config.get("Settings", "REJECT_DIR", fallback="./REJECTED/").strip("\"'")
        HIDDEN_DIR = config.get("Settings", "HIDDEN_DIR", fallback=".multidisco").strip("\"'")
        Quick_TIME = config.getboolean("Settings", "Quick_TIME", fallback=False)

        for d_path in [SOURCE_DIR, TARGET_DIR, TEMPOR_DIR, REDUMP_DIR, REJECT_DIR, STORED_DIR]:
            if not os.path.exists(d_path):
                os.makedirs(d_path, exist_ok=True)

        return True, "Configuration successfully loaded and paths verified."
    except (configparser.Error, OSError) as e:
        return False, f"Failed to parse configuration or create directories: {e}"


# ==============================================================================
# TUI / CUSTOM COMPONENTS & USER INTERFACE
# ==============================================================================
class CheckRow(Horizontal):
    class Changed(Message):
        def __init__(self, check_row: "CheckRow", value: bool) -> None:
            self.check_row = check_row
            self.value = value
            super().__init__()

    def __init__(self, text: str, id: str = None, value: bool = False, disabled: bool = False):
        super().__init__(id=id)
        self._text = text
        self._value = value
        self._disabled = disabled

    def compose(self) -> ComposeResult:
        char_mid = "X" if self._value else " "
        yield Static("[", id="box-open", markup=False)
        yield Static(char_mid, id="box-mid", markup=False)
        yield Static("]", id="box-close", markup=False)
        yield Static(self._text, id="box-text", markup=False)

    def on_mount(self) -> None:
        if self._disabled:
            self.add_class("disabled")
        else:
            self.remove_class("disabled")
            
        if self._value:
            self.add_class("checked")
        else:
            self.remove_class("checked")

    @property
    def value(self) -> bool:
        return self._value

    @value.setter
    def value(self, new_val: bool):
        self._value = new_val
        if self.is_mounted:
            mid = self.query_one("#box-mid", Static)
            mid.update("X" if self._value else " ")
        
        if self._value:
            self.add_class("checked")
        else:
            self.remove_class("checked")

    @property
    def disabled(self) -> bool:
        return self._disabled

    @disabled.setter
    def disabled(self, new_val: bool):
        self._disabled = new_val
        if self._disabled:
            self.add_class("disabled")
        else:
            self.remove_class("disabled")

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, new_text: str):
        self._text = new_text
        if self.is_mounted:
            txt_widget = self.query_one("#box-text", Static)
            txt_widget.update(self._text)

    def on_click(self) -> None:
        if not self._disabled:
            self.value = not self._value
            self.post_message(self.Changed(self, self._value))


class MainDashboard(Horizontal):
    """Griglia a 3 finestre: Sidebar a sinistra (Controlli), Tabella in alto a destra, Log in basso a destra"""
    
    def compose(self) -> ComposeResult:
        with Vertical(id="sidebar-pane"):
            yield Label("CONTROLS", classes="pane-title")
            yield Button("🔍 Scan Staging Dir", id="btn_scan", variant="primary")
            
            yield Label("Stats:", id="scan_stats_title")
            yield Label("Nessuna scansione effettuata.", id="scan_stats")
            
            yield Button("🚀 Start Conversion", id="btn_exec", variant="success", disabled=True)
            
        with Vertical(id="right-pane-container"):
            with Vertical(id="panel-top"):
                yield Label("ROM QUEUE", classes="pane-title")
                yield DataTable(id="rom_table", cursor_type="row")
                
            with Vertical(id="panel-bottom"):
                yield Label("CONVERSION CONSOLE", classes="pane-title")
                yield RichLog(id="console_log", highlight=True, markup=True)

    def on_mount(self) -> None:
        table = self.query_one("#rom_table", DataTable)
        table.add_columns(
            "RDY", "System", "Game", "ZIP", "EXT", 
            "CRC", "CUE", "SBI", "SET", "Create", "Note"
        )
        
        log = self.query_one("#console_log", RichLog)
        log.write("[bold cyan]Dashboard pronta.[/bold cyan] In attesa della scansione della directory sorgente...")

    @on(Button.Pressed, "#btn_scan")
    def action_scan_directory(self) -> None:
        log = self.query_one("#console_log", RichLog)
        table = self.query_one("#rom_table", DataTable)
        
        table.clear()
        log.clear()
        log.write(f"[yellow]Start scanning {SOURCE_DIR} [/yellow]")
        self.query_one("#btn_scan", Button).disabled = True
        self.query_one("#btn_exec", Button).disabled = True
        
        self.run_scanner_engine()


    @work(thread=True)
    def run_scanner_engine(self) -> None:
        if not os.path.exists(SOURCE_DIR):
            self.app.call_from_thread(self.log_to_console, f"[red]Error: directory {SOURCE_DIR} not found![/red]")
            self.app.call_from_thread(self.finalize_scan, 0, 0, 0, False)
            return

        files = [f for f in os.listdir(SOURCE_DIR) if os.path.isfile(os.path.join(SOURCE_DIR, f))]
        total_files = len(files)
        valid_items = 0
        warning_items = 0
        error_items = 0
        
        self.app.call_from_thread(self.log_to_console, f"Analyzing {total_files} files in {SOURCE_DIR}")

        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
        except sqlite3.Error as e:
            self.app.call_from_thread(self.log_to_console, f"[red]Database error: {e}[/red]")
            self.app.call_from_thread(self.finalize_scan, total_files, 0, total_files, False)
            return

        self.conversion_matrix = []
        detected_sets = {}

        for filename in files:
            filepath = os.path.join(SOURCE_DIR, filename)
            ext = os.path.splitext(filename)[1].lower()
            
            rdy_status = "OK" 
            sys_name, game_name, note = "???", filename, ""
            zip_type, img_ext, cue_stat, sbi_stat, set_stat = "-", "-", "-", "-", ""
            create_cmd = "CD"
            
            matched_row = None
            total_discs = None
            disc_num = None
            file_crc = "-"

            if ext == ".cue":
                continue

            if "(track" in filename.lower() and "track 1" not in filename.lower():
                continue

            # ==========================================
            # 1. ARCHIVI COMPRESSI (ZIP, 7Z, RAR)
            # ==========================================
            if ext in [".zip", ".7z", ".rar"]:
                zip_type = ext[1:].upper()
                try:
                    rom_infos = []
                    has_cue_inside = False
                    
                    if ext == ".zip":
                        with zipfile.ZipFile(filepath, 'r') as zf:
                            namelist = zf.namelist()
                            rom_infos = [(i.filename, format(i.CRC & 0xFFFFFFFF, '08x')) for i in zf.infolist() if i.filename.lower().endswith(('.iso', '.bin'))]
                            has_cue_inside = any(n.lower().endswith('.cue') for n in namelist)
                    elif ext == ".7z":
                        with py7zr.SevenZipFile(filepath, mode='r') as zf:
                            files_info = zf.list()
                            rom_infos = [(f.filename, format(f.crc32 & 0xFFFFFFFF, '08x')) for f in files_info if f.filename.lower().endswith(('.iso', '.bin'))]
                            has_cue_inside = any(f.filename.lower().endswith('.cue') for f in files_info)
                    elif ext == ".rar":
                        with rarfile.RarFile(filepath) as rf:
                            namelist = rf.namelist()
                            rom_infos = [(n, format(rf.getinfo(n).CRC & 0xFFFFFFFF, '08x')) for n in namelist if n.lower().endswith(('.iso', '.bin'))]
                            has_cue_inside = any(n.lower().endswith('.cue') for n in namelist)

                    if rom_infos:
                        img_ext = os.path.splitext(rom_infos[0][0])[1][1:].upper()
                        found_tracks_count = len(rom_infos)
                        file_crc = rom_infos[0][1]
                        
                        valid_match_found = False
                        for fname, crc_hex in rom_infos:
                            fname_lower = fname.lower()
                            if found_tracks_count > 1 and "track" in fname_lower and "track 1" not in fname_lower:
                                continue

                            cursor.execute("SELECT system, game_name, has_sbi, rom_name FROM dat_entries WHERE upper(crc) = ?", (crc_hex.upper(),))
                            rows = cursor.fetchall()
                            for r in rows:
                                rom_n = r[3].lower() if len(r) > 3 else ""
                                if "track" not in rom_n or "track 1" in rom_n:
                                    matched_row = r
                                    valid_match_found = True
                                    break
                            if valid_match_found:
                                break

                        if not valid_match_found:
                            rdy_status = "KO"
                            note = f"Track 1 CRC not found in Redump DB"
                            error_items += 1
                        else:
                            sys_name, game_name, has_sbi = matched_row[0], matched_row[1], matched_row[2]
                            if found_tracks_count > 1:
                                cursor.execute("SELECT COUNT(*) FROM dat_entries WHERE game_name = ? AND (rom_name LIKE '%.bin' OR rom_name LIKE '%.iso')", (game_name,))
                                expected_res = cursor.fetchone()
                                expected_tracks = expected_res[0] if expected_res else found_tracks_count
                                
                                if found_tracks_count == expected_tracks:
                                    note = f"multitrack disk: {found_tracks_count} tracks found, {expected_tracks} expected"
                                else:
                                    rdy_status = "WRN"
                                    note = f"multitrack disk mismatch: {found_tracks_count} tracks found, {expected_tracks} expected"
                                    warning_items += 1

                        if matched_row and rdy_status != "KO":
                            if rdy_status != "WRN":
                                valid_items += 1
                            sbi_stat = "SI" if has_sbi else "-"
                            if img_ext == "BIN" or has_cue_inside:
                                cue_stat = "L" if has_cue_inside else "R"
                    else:
                        rdy_status = "KO"
                        note = "No valid ISO/BIN file inside archive"
                        error_items += 1
                except Exception:
                    rdy_status = "KO"
                    note = "Corrupted or password protected archive"
                    error_items += 1

            # ==========================================
            # 2. FILE SCOMPATTI (RAW: .iso, .bin)
            # ==========================================
            elif ext in [".iso", ".bin"]:
                zip_type = "RAW"
                img_ext = ext[1:].upper()
                
                if ext == ".bin" and "(track" in filename.lower() and "track 1" not in filename.lower():
                    continue

                if ext == ".bin":
                    base_prefix = filename.rsplit(' (Track', 1)[0].rsplit(' (disc', 1)[0] if '(Track' in filename or '(disc' in filename else os.path.splitext(filename)[0]
                    local_bins = [f for f in files if f.startswith(base_prefix) and f.lower().endswith('.bin')]
                    found_tracks_count = len(local_bins)
                else:
                    found_tracks_count = 1

                file_crc = calculate_file_crc32(filepath)
                if file_crc:
                    cursor.execute("SELECT system, game_name, has_sbi, rom_name FROM dat_entries WHERE upper(crc) = ?", (file_crc.upper(),))
                    rows = cursor.fetchall()
                    
                    valid_match_found = False
                    for r in rows:
                        rom_n = r[3].lower() if len(r) > 3 else ""
                        if "track" not in rom_n or "track 1" in rom_n:
                            matched_row = r
                            valid_match_found = True
                            break
                    
                    if valid_match_found:
                        sys_name, game_name, has_sbi = matched_row[0], matched_row[1], matched_row[2]
                        
                        if found_tracks_count > 1:
                            cursor.execute("SELECT COUNT(*) FROM dat_entries WHERE game_name = ? AND (rom_name LIKE '%.bin' OR rom_name LIKE '%.iso')", (game_name,))
                            expected_res = cursor.fetchone()
                            expected_tracks = expected_res[0] if expected_res else found_tracks_count
                            
                            if found_tracks_count == expected_tracks:
                                note = f"multitrack disk: {found_tracks_count} tracks found, {expected_tracks} expected"
                            else:
                                rdy_status = "WRN"
                                note = f"multitrack disk mismatch: {found_tracks_count} tracks found, {expected_tracks} expected"
                                warning_items += 1
                        
                        if rdy_status != "WRN":
                            valid_items += 1
                        sbi_stat = "SI" if has_sbi else "-"
                        
                        if ext == ".bin":
                            cue_file = os.path.splitext(filename)[0].rsplit(' (Track', 1)[0] + ".cue"
                            if cue_file in files or (os.path.splitext(filename)[0] + ".cue") in files:
                                cue_stat = "L"
                            else:
                                cursor.execute("SELECT 1 FROM dat_entries WHERE game_name = ? AND rom_name LIKE '%.cue'", (game_name,))
                                if cursor.fetchone():
                                    cue_stat = "R"
                                else:
                                    cue_stat = "-"
                                    rdy_status = "KO"
                                    note = "Errore: file bin senza cue file associato"
                                    error_items += 1
                                    valid_items -= 1
                    else:
                        rdy_status = "KO"
                        note = f"CRC {file_crc.upper()} not found in Redump DB"
                        error_items += 1
                else:
                    rdy_status = "KO"
                    note = "Failed to calculate CRC"
                    error_items += 1

            elif ext in [".img", ".ccd"]:
                zip_type = "RAW"
                img_ext = ext[1:].upper()
                rdy_status = "KO"
                note = "CloneCD format not supported"
                error_items += 1
            else:
                continue

            # --- LOGICA CORRETTA PER CREATE_CMD ---
            cue_source_candidate = os.path.splitext(filepath)[0] + ".cue"
            has_local_cue = os.path.exists(cue_source_candidate)

            if sys_name == "PSP":
                create_cmd = "CSO"
            elif sys_name == "PSX":
                create_cmd = "CD"
            elif sys_name == "PS2":
                # Se è PS2 ma ha un file .cue locale, estensione .bin o cue stat attivo, è un CD (es. LEGO Star Wars)
                if has_local_cue or ext in ['.bin', '.img'] or cue_stat in ["L", "SI", "R"]:
                    create_cmd = "CD"
                else:
                    create_cmd = "DVD"
            else:
                create_cmd = "CD"

            if matched_row:
                match_disc = re.search(r'\(Disc\s+(\d+)\s+of\s+(\d+)\)|\(Disc\s+(\d+)\)', game_name, re.IGNORECASE)
                if match_disc:
                    if match_disc.group(1) and match_disc.group(2):
                        disc_num = int(match_disc.group(1))
                        total_discs = int(match_disc.group(2))
                        set_stat = f"{disc_num}/{total_discs}"
                    elif match_disc.group(3):
                        disc_num = int(match_disc.group(3))
                        base_name = re.sub(r'\(Disc\s+\d+\).*', '', game_name).strip()
                        cursor.execute("SELECT COUNT(DISTINCT game_name) FROM dat_entries WHERE game_name LIKE ? AND game_name LIKE '%(Disc %'", (f"{base_name}%",))
                        res_total = cursor.fetchone()
                        total_discs = res_total[0] if res_total and res_total[0] > 0 else 1
                        set_stat = f"{disc_num}/{total_discs}"

                    if total_discs and disc_num:
                        base_key = re.sub(r'\(Disc\s+.*\)', '', game_name).strip()
                        if base_key not in detected_sets:
                            detected_sets[base_key] = set()
                        detected_sets[base_key].add(disc_num)
                else:
                    set_stat = ""

            row_matrix_entry = [
                filename,
                zip_type,
                game_name,
                file_crc,
                disc_num,
                cue_stat,
                sys_name,
                img_ext,
                found_tracks_count if 'found_tracks_count' in locals() else 1,
                create_cmd,
                rdy_status,
                note,
                sbi_stat
            ]
            self.conversion_matrix.append(row_matrix_entry)

        for row in self.conversion_matrix:
            game_name = row[2]
            match_disc = re.search(r'\(Disc\s+(\d+)\s+of\s+(\d+)\)|\(Disc\s+(\d+)\)', game_name, re.IGNORECASE)
            if match_disc:
                base_key = re.sub(r'\(Disc\s+.*\)', '', game_name).strip()
                cursor.execute("SELECT COUNT(DISTINCT game_name) FROM dat_entries WHERE game_name LIKE ? AND game_name LIKE '%(Disc %'", (f"{base_key}%",))
                res_total = cursor.fetchone()
                expected_total = res_total[0] if res_total and res_total[0] > 0 else 1
                found_discs = detected_sets.get(base_key, set())
                
                missing_discs = sorted(list(set(range(1, expected_total + 1)) - found_discs))
                
                if row[10] == "OK":
                    if len(missing_discs) > 0:
                        row[10] = "WRN"
                        missing_str = ", ".join(map(str, missing_discs))
                        row[11] = f"Incomplete set: missing disc(s): {missing_str}"
                        warning_items += 1
                        valid_items -= 1
                    elif not row[11]:
                        row[11] = "Set completo"

        conn.close()
        
        self.conversion_matrix.sort(key=lambda x: (x[2], x[4] if x[4] is not None else 0))

        self.app.call_from_thread(self.app.clear_table)

        for row in self.conversion_matrix:
            st = row[10]
            if st == "OK":
                rdy_glyph = "[green]+++[/green]"
            elif st == "WRN":
                rdy_glyph = "[yellow]WRN[/yellow]"
            else:
                rdy_glyph = "[red]---[/red]"

            match_d = re.search(r'\(Disc\s+(\d+)\s+of\s+(\d+)\)|\(Disc\s+(\d+)\)', row[2], re.IGNORECASE)
            display_set = "-/-"
            if match_d:
                if match_d.group(1) and match_d.group(2):
                    display_set = f"{match_d.group(1)}/{match_d.group(2)}"
                elif match_d.group(3):
                    base_k = re.sub(r'\(Disc\s+\d+\).*', '', row[2]).strip()
                    conn_t = sqlite3.connect(DB_NAME)
                    cur_t = conn_t.cursor()
                    cur_t.execute("SELECT COUNT(DISTINCT game_name) FROM dat_entries WHERE game_name LIKE ? AND game_name LIKE '%(Disc %'", (f"{base_k}%",))
                    r_tot = cur_t.fetchone()
                    tot_d = r_tot[0] if r_tot and r_tot[0] > 0 else 1
                    conn_t.close()
                    display_set = f"{match_d.group(3)}/{tot_d}"
            else:
                display_set = ""

            row_data = (
                rdy_glyph, 
                row[6], 
                row[2], 
                row[1], 
                row[7], 
                row[3], 
                row[5], 
                row[12], 
                display_set, 
                row[9], 
                row[11] 
            )
            self.app.call_from_thread(self.add_table_row, row_data)

        all_green = (valid_items > 0 and error_items == 0 and warning_items == 0)
        self.app.call_from_thread(self.finalize_scan, total_files, valid_items, warning_items, error_items, all_green)
    
    
    def log_to_console(self, message: str) -> None:
        self.query_one("#console_log", RichLog).write(message)

    def add_table_row(self, row_data: tuple) -> None:
        self.query_one("#rom_table", DataTable).add_row(*row_data)


    def finalize_scan(self, total: int, valid: int, warnings: int, errors: int, enable_exec: bool) -> None:
        self.query_one("#btn_scan", Button).disabled = False
        
        exec_btn = self.query_one("#btn_exec", Button)
        exec_btn.disabled = not enable_exec
            
        stats_label = self.query_one("#scan_stats", Label)
        stats_label.update(
            f"Analyzed : {total}\n"
            f"Valid    : {valid}\n"
            f"Warnings : {warnings}\n"
            f"Errors   : {errors}"
        )
        
        if enable_exec:
            self.log_to_console("[green]✔ Scan completed. All files are valid (green RDY). Conversion unlocked![/green]")
        else:
            self.log_to_console("[yellow]⚠ Scan completed with anomalies, missing discs or invalid files. Resolve issues before converting.[/yellow]")


    @on(Button.Pressed, "#btn_exec")
    @work(thread=True)
    def action_execute_conversion(self) -> None:
        log = self.query_one("#console_log", RichLog)
        log.write("[bold magenta]🚀 Starting conversion process... Do not close the application.[/bold magenta]")
        
        self.app.call_from_thread(lambda: self.query_one("#btn_exec", Button).__setattr__("disabled", True))
        self.app.call_from_thread(lambda: self.query_one("#btn_scan", Button).__setattr__("disabled", True))

        if not hasattr(self, "conversion_matrix") or not self.conversion_matrix:
            log.write("[red]Error: No conversion matrix found. Run a scan first.[/red]")
            self.app.call_from_thread(lambda: self.query_one("#btn_scan", Button).__setattr__("disabled", False))
            return

        total_items = len(self.conversion_matrix)
        success_count = 0

        for idx, row in enumerate(self.conversion_matrix, 1):
            filename = row[0]
            zip_type = row[1]
            game_name = row[2]
            file_crc = row[3]
            disc_num = row[4]
            cue_stat = row[5]
            sys_name = row[6]
            img_ext = row[7]
            tracks_count = row[8]
            create_cmd = row[9]
            rdy_status = row[10]
            sbi_stat = row[12]

            if rdy_status == "KO":
                log.write(f"[yellow]Skipping [{idx}/{total_items}] {filename}: invalid.[/yellow]")
                continue

            log.write(f"\n[cyan]----------------------------------------[/cyan]")
            log.write(f"[cyan]Processing [{idx}/{total_items}]: {game_name} ({sys_name}) [CMD: {create_cmd}][/cyan]")

            source_filepath = os.path.join(SOURCE_DIR, filename)
            sys_lower = sys_name.lower()
            target_sys_dir = os.path.join(TARGET_DIR, sys_lower)
            archive_sys_dir = os.path.join(STORED_DIR, sys_lower)
            os.makedirs(target_sys_dir, exist_ok=True)
            os.makedirs(archive_sys_dir, exist_ok=True)

            temp_work_dir = os.path.join(TEMPOR_DIR, f"work_{int(time.time() * 1000)}")
            os.makedirs(temp_work_dir, exist_ok=True)

            conversion_success = False
            base_prefix_name = ""

            try:
                log.write(f"  -> Extracting/Preparing files...")
                extracted_files = []

                if zip_type in ["ZIP", "7Z", "RAR"]:
                    if zip_type == "ZIP":
                        with zipfile.ZipFile(source_filepath, 'r') as zf:
                            zf.extractall(temp_work_dir)
                    elif zip_type == "7Z":
                        with py7zr.SevenZipFile(source_filepath, mode='r') as zf:
                            zf.extractall(temp_work_dir)
                    elif zip_type == "RAR":
                        with rarfile.RarFile(source_filepath) as rf:
                            rf.extractall(temp_work_dir)
                    
                    for root_w, _, files_w in os.walk(temp_work_dir):
                        for fw in files_w:
                            extracted_files.append(os.path.join(root_w, fw))
                else:
                    base_filename_lower = os.path.basename(source_filepath).lower()
                    if "(track" in base_filename_lower:
                        base_prefix_name = os.path.basename(source_filepath).rsplit(' (Track', 1)[0].rsplit(' (track', 1)[0]
                    else:
                        base_prefix_name = os.path.splitext(os.path.basename(source_filepath))[0]

                    for f_src in os.listdir(SOURCE_DIR):
                        if f_src.lower().startswith(base_prefix_name.lower()):
                            f_src_path = os.path.join(SOURCE_DIR, f_src)
                            if os.path.isfile(f_src_path):
                                shutil.copy(f_src_path, temp_work_dir)
                                extracted_files.append(os.path.join(temp_work_dir, f_src))

                cue_file_path = None
                main_img_path = None

                for ef in extracted_files:
                    if ef.lower().endswith('.cue'):
                        cue_file_path = ef
                    elif ef.lower().endswith(('.iso', '.bin', '.img', '.mdf')):
                        if not main_img_path:
                            main_img_path = ef

                # NORMALIZATION & REDUMP CUE MATCHING
                if img_ext == "BIN" and not cue_file_path and main_img_path:
                    old_bin_path = main_img_path
                    new_bin_filename = f"{game_name}.bin"
                    new_bin_path = os.path.join(temp_work_dir, new_bin_filename)
                    
                    if old_bin_path != new_bin_path:
                        shutil.move(old_bin_path, new_bin_path)
                        main_img_path = new_bin_path
                        log.write(f"  -> Normalized binary in temp: {new_bin_filename}")

                    redump_cue_path = os.path.join(REDUMP_DIR, sys_name, "CUE", f"{game_name}.cue")
                    if os.path.exists(redump_cue_path):
                        cue_file_path = os.path.join(temp_work_dir, f"{game_name}.cue")
                        shutil.copy(redump_cue_path, cue_file_path)
                        log.write(f"  -> Redump CUE successfully copied.")
                    else:
                        log.write(f"  [red]Error: CUE file not found in Redump for '{game_name}'![/red]")

                if create_cmd == "CD" and (not cue_file_path or not os.path.exists(cue_file_path)):
                    log.write(f"  [red]Conversion aborted: Missing CUE. Source files were NOT touched.[/red]")
                    shutil.rmtree(temp_work_dir, ignore_errors=True)
                    continue

                output_ext = ".cso" if create_cmd == "CSO" else ".chd"
                final_output_filename = f"{game_name}{output_ext}"
                temp_output_filepath = os.path.join(temp_work_dir, final_output_filename)

                if create_cmd == "CSO":
                    log.write(f"  -> Converting to CSO (maxcso)...")
                    cmd = ["maxcso", "--quiet", main_img_path, "-o", temp_output_filepath]
                    res = subprocess.run(cmd, capture_output=True, text=True)
                    if res.returncode == 0:
                        conversion_success = True
                    else:
                        log.write(f"  [red]maxcso error: {res.stderr}[/red]")

                elif create_cmd in ["CD", "DVD"]:
                    log.write(f"  -> Converting to CHD (chdman create{create_cmd.lower()})...")
                    input_for_chd = cue_file_path if (cue_file_path and create_cmd == "CD") else main_img_path
                    
                    cmd = ["chdman", f"create{create_cmd.lower()}", "-i", input_for_chd, "-o", temp_output_filepath, "--force"]
                    res = subprocess.run(cmd, capture_output=True, text=True)
                    if res.returncode == 0:
                        conversion_success = True
                    else:
                        log.write(f"  [red]chdman error: {res.stderr.strip()}[/red]")

                if not conversion_success or not os.path.exists(temp_output_filepath):
                    log.write(f"  [red]Conversion failed for {game_name}. Original source files are safe and were NOT touched.[/red]")
                    shutil.rmtree(temp_work_dir, ignore_errors=True)
                    continue

                base_key_set = re.sub(r'\(Disc\s+.*\)', '', game_name).strip()
                is_multidisc = disc_num is not None
                hidden_subfolder = None

                if is_multidisc:
                    hidden_subfolder = os.path.join(target_sys_dir, HIDDEN_DIR, base_key_set)
                    os.makedirs(hidden_subfolder, exist_ok=True)
                    final_target_path = os.path.join(hidden_subfolder, final_output_filename)
                    shutil.move(temp_output_filepath, final_target_path)
                    
                    m3u_filepath = os.path.join(target_sys_dir, f"{base_key_set}.m3u")
                    existing_discs_chd = sorted([f for f in os.listdir(hidden_subfolder) if f.lower().endswith(('.chd', '.cso'))])
                    with open(m3u_filepath, "w", encoding="utf-8") as m3u_file:
                        for d_chd in existing_discs_chd:
                            m3u_file.write(f"{HIDDEN_DIR}/{base_key_set}/{d_chd}\n")
                    log.write(f"  -> Multi-disc file added and .m3u updated.")
                else:
                    final_target_path = os.path.join(target_sys_dir, final_output_filename)
                    shutil.move(temp_output_filepath, final_target_path)
                    log.write(f"  -> Converted file moved to TARGET.")

                if sys_name == "PSX" and sbi_stat == "SI":
                    sbi_source_path = os.path.join(REDUMP_DIR, "PSX", "SBI", f"{game_name}.sbi")
                    if os.path.exists(sbi_source_path):
                        sbi_target_dest = os.path.join(hidden_subfolder if is_multidisc else target_sys_dir, f"{game_name}.sbi")
                        shutil.copy(sbi_source_path, sbi_target_dest)
                        log.write(f"  -> Associated protected .SBI file copied.")

                log.write(f"  -> Archiving original files to 7z format (STORED)...")
                archive_7z_path = os.path.join(archive_sys_dir, f"{game_name}.7z")
                with py7zr.SevenZipFile(archive_7z_path, 'w') as archive:
                    for root_w, _, files_w in os.walk(temp_work_dir):
                        for fw in files_w:
                            full_fw = os.path.join(root_w, fw)
                            if full_fw != final_target_path and not fw.endswith(('.chd', '.cso')):
                                relname = os.path.basename(full_fw)
                                archive.write(full_fw, arcname=relname)

                shutil.rmtree(temp_work_dir, ignore_errors=True)
                
                if zip_type == "RAW" and base_prefix_name:
                    for f_src in os.listdir(SOURCE_DIR):
                        if f_src.lower().startswith(base_prefix_name.lower()):
                            f_src_path = os.path.join(SOURCE_DIR, f_src)
                            if os.path.isfile(f_src_path):
                                os.remove(f_src_path)
                else:
                    if os.path.exists(source_filepath):
                        os.remove(source_filepath)

                log.write(f"  -> Original source file safely removed from SOURCE.")
                success_count += 1
                log.write(f"  [green]✔ 100% Successfully completed![/green]")

            except Exception as e:
                log.write(f"  [red]Critical error during processing of {filename}: {e}. No source files were touched.[/red]")
                if os.path.exists(temp_work_dir):
                    shutil.rmtree(temp_work_dir, ignore_errors=True)

        log.write(f"\n[bold green]🎉 Conversion finished! {success_count} out of {total_items} items processed.[/bold green]")
        self.app.call_from_thread(lambda: self.query_one("#btn_scan", Button).__setattr__("disabled", False))

    
class RomConvertApp(App):
    TITLE = "RomConvert 2.0"
    SUB_TITLE = "Pre-Flight Checklist"

    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+t", "toggle_dark", "Toggle Light/Dark Mode"),
    ]

    CSS = """
    Screen { layout: vertical; }
    
    #top-pane {
        height: auto;
        border: solid green;
        padding: 0 2 1 2;
        margin: 1 2 0 2;
        align: left top;
    }
    
    #bottom-pane {
        height: 1fr;
        border: solid cyan;
        padding: 0 2;
        margin: 1 2;
        layout: vertical;
    }
    
    #countdown_banner {
        height: 1;
        content-align: center middle;
        color: yellow;
        text-style: bold;
        margin-top: 1;
    }
    
    MainDashboard {
        layout: horizontal;
        height: 1fr;
        margin: 1 2;
    }
    
    #sidebar-pane {
        width: 30;
        border: solid yellow;
        padding: 1;
        margin-right: 1;
    }
    
    #right-pane-container {
        width: 1fr;
        layout: vertical;
        height: 1fr;
    }
    
    #panel-top {
        height: 1fr;
        border: solid cyan;
        padding: 1;
        margin-bottom: 1;
    }
    
    #panel-bottom {
        height: 1fr;
        border: solid green;
        padding: 1;
    }
    
    .pane-title {
        text-style: bold;
        color: yellow;
        margin-bottom: 1;
    }
    
    #sidebar-pane Button {
        width: 100%;
    }
    
    #btn_scan {
        margin-bottom: 1;
    }
    
    #btn_exec {
        margin-top: 2;
    }
    
    #scan_stats_title {
        margin-top: 1;
        text-style: bold;
        color: yellow;
    }
    
    #scan_stats {
        color: auto;
    }

    Screen:dark .panel-title { text-style: bold; color: yellow; margin-bottom: 1; }
    Screen:light .panel-title { text-style: bold; color: #000080; margin-bottom: 1; }
    
    CheckRow { height: 1; width: 100%; margin-bottom: 0; padding: 0; }
    CheckRow:hover { background: $boost; }
    CheckRow.disabled { opacity: 0.4; }
    
    #box-open, #box-close { width: 1; text-style: bold; }
    #box-mid { width: 1; text-style: bold; text-align: center; }
    #box-text { width: 1fr; padding-left: 1; }

    Screen:dark #box-open, Screen:dark #box-close { color: yellow; }
    Screen:dark CheckRow.checked #box-mid { color: green; }
    Screen:light #box-open, Screen:light #box-close { color: black; }
    Screen:light CheckRow.checked #box-mid { color: blue; }
    """

    def __init__(self):
        super().__init__()
        self.persistent_logs = []
        self.can_transition = False
        self.countdown_left = 10
        self.countdown_interval = None

    def on_key(self, event) -> None:
        if event.key.lower() == "g" and getattr(self, "can_transition", False):
            self.action_skip_to_dashboard()

    def add_log(self, message: str, persistent: bool = True):
        def _update():
            try:
                log = self.query_one("#system_log", RichLog)
                if persistent:
                    self.persistent_logs.append(message)
                    log.write(message)
                else:
                    log.clear()
                    for line in self.persistent_logs:
                        log.write(line)
                    log.write(message)
            except Exception:
                pass
        
        try:
            self.call_from_thread(_update)
        except RuntimeError:
            _update()
        
    def clear_transient_log(self):
        def _clear():
            try:
                log = self.query_one("#system_log", RichLog)
                log.clear()
                for line in self.persistent_logs:
                    log.write(line)
            except Exception:
                pass
                
        try:
            self.call_from_thread(_clear)
        except RuntimeError:
            _clear()

    def compose(self) -> ComposeResult:
        yield Header()
        
        with Vertical(id="top-pane"):
            yield Label("PRE-FLIGHT CHECKLIST (Interactive)", classes="panel-title")
            yield CheckRow("1. Database verification", id="chk_db", value=False)
            yield CheckRow("2. Download and parse DAT files (Requires DB)", id="chk_dat", value=False, disabled=True)
            yield CheckRow("3. Verify CUE/SBI directory structure (Requires DAT)", id="chk_dirs", value=False, disabled=True)
            yield CheckRow("4. Verify CUE/SBI files", id="chk_cue_sbi", value=False, disabled=True)

        with Vertical(id="bottom-pane"):
            yield Label("SYSTEM LOGS", classes="panel-title")
            yield RichLog(id="system_log", highlight=True, markup=True)
            yield Static("", id="countdown_banner")
            
        yield Footer()

    def print_startup_logs(self) -> None:
        self.add_log("[bold blue]RomConvert 2.0 started in TUI mode.[/bold blue]")
        
        cfg_success, cfg_msg = RC_Oper_Config_Load()
        if cfg_success:
            self.add_log(f"[green]✔ {cfg_msg}[/green]")
            self.add_log(f"  - Source    : {SOURCE_DIR}")
            self.add_log(f"  - Target    : {TARGET_DIR}")
            self.add_log(f"  - Temporary : {TEMPOR_DIR}")
            self.add_log(f"  - Stored    : {STORED_DIR}")
            self.add_log(f"  - Reject    : {REJECT_DIR}")
            self.add_log(f"  - ReDump    : {REDUMP_DIR}")
        else:
            self.add_log(f"[red]CRITICAL ERROR: {cfg_msg}[/red]")

        self.add_log("Analyzing environment...")

    def check_directories_status(self) -> bool:
        REQUIRED_STRUCTURE = {
            "PSX": ["CUE", "SBI"],
            "PS2": ["CUE"],
            "PSP": []
        }
        for plat, subfolders in REQUIRED_STRUCTURE.items():
            plat_path = os.path.join(REDUMP_DIR, plat)
            if not os.path.exists(plat_path):
                return False
            for sub in subfolders:
                if not os.path.exists(os.path.join(plat_path, sub)):
                    return False
        return True

    def get_detailed_zip_mapping(self) -> dict:
        details = {
            "PSX/CUE": {"zip_name": None, "expected": 0, "found": 0},
            "PSX/SBI": {"zip_name": None, "expected": 0, "found": 0},
            "PS2/CUE": {"zip_name": None, "expected": 0, "found": 0}
        }
        if not os.path.exists(REDUMP_DIR):
            return details

        try:
            for f in os.listdir(REDUMP_DIR):
                if f.lower().endswith(".zip"):
                    parts = [p.strip().lower() for p in f.split('-')]
                    if len(parts) >= 2:
                        system_name = parts[1]
                        f_low = f.lower()
                        zip_path = os.path.join(REDUMP_DIR, f)
                        
                        try:
                            with zipfile.ZipFile(zip_path, 'r') as zf:
                                namelist = zf.namelist()
                                if system_name == "playstation" and ("cue" in f_low or "sheet" in f_low):
                                    details["PSX/CUE"]["zip_name"] = f
                                    details["PSX/CUE"]["expected"] = len([n for n in namelist if n.lower().endswith('.cue')])
                                elif system_name == "playstation" and "sbi" in f_low:
                                    details["PSX/SBI"]["zip_name"] = f
                                    details["PSX/SBI"]["expected"] = len([n for n in namelist if n.lower().endswith('.sbi')])
                                elif system_name == "playstation 2" and ("cue" in f_low or "sheet" in f_low):
                                    details["PS2/CUE"]["zip_name"] = f
                                    details["PS2/CUE"]["expected"] = len([n for n in namelist if n.lower().endswith('.cue')])
                        except zipfile.BadZipFile:
                            pass
        except OSError:
            pass

        targets = [
            ("PSX/CUE", os.path.join(REDUMP_DIR, "PSX", "CUE")),
            ("PSX/SBI", os.path.join(REDUMP_DIR, "PSX", "SBI")),
            ("PS2/CUE", os.path.join(REDUMP_DIR, "PS2", "CUE"))
        ]
        for key, path in targets:
            if os.path.exists(path):
                details[key]["found"] = len([n for n in os.listdir(path) if not n.startswith('.')])
            else:
                details[key]["found"] = 0

        return details

    def evaluate_cue_sbi_scenarios(self) -> int:
        details = self.get_detailed_zip_mapping()
        
        zip_psx_cue = details["PSX/CUE"]["zip_name"] is not None
        zip_psx_sbi = details["PSX/SBI"]["zip_name"] is not None
        zip_ps2_cue = details["PS2/CUE"]["zip_name"] is not None
        all_zips_present = zip_psx_cue and zip_psx_sbi and zip_ps2_cue

        empty_folders = any(details[k]["found"] == 0 for k in details.keys())
        inconsistent = any(details[k]["expected"] > 0 and details[k]["found"] != details[k]["expected"] for k in details.keys())

        self.add_log("[cyan]--- CUE/SBI DETAILED DIAGNOSTICS ---[/cyan]")
        for k, info in details.items():
            z_name = info["zip_name"] if info["zip_name"] else "[red]NOT FOUND[/red]"
            self.add_log(f"  - [{k}] Zip: {z_name} | Expected: {info['expected']} | Found on disk: {info['found']}")

        if empty_folders:
            return 4
        if not all_zips_present:
            return 3
        if inconsistent:
            return 2
        return 1

    def run_final_verification(self) -> None:
        self.add_log("Running final verification and updating SBI flags in database...")
        RC_Oper_Update_SBI_Flags(DB_NAME, REDUMP_DIR)
        
        chk_cue_sbi = self.query_one("#chk_cue_sbi", CheckRow)
        chk_cue_sbi.text = "4. CUE/SBI files verified"
        chk_cue_sbi.value = True
        chk_cue_sbi.disabled = True
        
        self.add_log("[green]✔ CUE/SBI files successfully verified and database updated.[/green]")
        self.add_log("\n[bold magenta]*** ALL PRE-FLIGHT CHECKS PASSED SUCCESSFULLY ***[/bold magenta]")
        
        self.can_transition = True
        self.countdown_left = 10
        
        banner = self.query_one("#countdown_banner", Static)
        banner.update(f"✨ Transitioning to dashboard in {self.countdown_left}s... (Press \\[G] to proceed immediately)")
        
        self.countdown_interval = self.set_interval(1.0, self.tick_countdown)

    def tick_countdown(self) -> None:
        if not self.can_transition:
            return
        
        self.countdown_left -= 1
        banner = self.query_one("#countdown_banner", Static)
        
        if self.countdown_left > 0:
            banner.update(f"✨ Transitioning to dashboard in {self.countdown_left}s... (Press \\[G] to proceed immediately)")
        else:
            if self.countdown_interval:
                self.countdown_interval.stop()
                self.countdown_interval = None
            self.action_skip_to_dashboard()

    def clear_table(self) -> None:
        """Pulisce la tabella principale dei ROM."""
        try:
            table = self.query_one("#rom_table", DataTable)
            table.clear()
        except Exception:
            pass

    def action_skip_to_dashboard(self) -> None:
        if not self.can_transition:
            return
        self.can_transition = False
        
        if self.countdown_interval:
            self.countdown_interval.stop()
            self.countdown_interval = None

        self.sub_title = "Main Dashboard"

        self.query_one("#top-pane").remove()
        self.query_one("#bottom-pane").remove()
        self.mount(MainDashboard())

    def on_mount(self) -> None:
        chk_db = self.query_one("#chk_db", CheckRow)
        chk_dat = self.query_one("#chk_dat", CheckRow)
        chk_dirs = self.query_one("#chk_dirs", CheckRow)

        def run_dirs_verification_automatic():
            self.add_log("Verifying CUE/SBI directory structure...")
            REQUIRED_STRUCTURE = {"PSX": ["CUE", "SBI"], "PS2": ["CUE"], "PSP": []}
            results = []
            for plat, subfolders in REQUIRED_STRUCTURE.items():
                plat_path = os.path.join(REDUMP_DIR, plat)
                os.makedirs(plat_path, exist_ok=True)
                for sub in subfolders:
                    target_path = os.path.join(plat_path, sub)
                    if os.path.exists(target_path):
                        status = "Already present"
                    else:
                        os.makedirs(target_path, exist_ok=True)
                        status = "Created"
                    results.append((f"{plat}/{sub}", status))

            for key, status in results:
                self.add_log(f"  - {key:<10} : {status}")

            chk_dirs.text = "3. CUE/SBI directory structure verified"
            chk_dirs.value = True
            chk_dirs.disabled = True

            self.add_log("[green]✔ CUE/SBI directory structure successfully verified.[/green]")
            
            delay = 0.01 if Quick_TIME else 1.0
            self.set_timer(delay, self.evaluate_step_4_on_startup)

        def run_dat_verification():
            self.add_log("Performing DAT files verification...")
            has_data, stats = RC_Oper_DAT_Check_Records()
            
            if has_data:
                self.add_log("[green]✔ DAT files already present in database:[/green]")
                for sys_name, data in stats.items():
                    if data["records"] > 0:
                        self.add_log(f"  - {sys_name}: {data['records']:>6,} records over {data['discs']:>6,} discs")
                
                chk_dat.text = "2. DAT files verified"
                chk_dat.value = True
                chk_dat.disabled = True
                
                REQUIRED_STRUCTURE = {"PSX": ["CUE", "SBI"], "PS2": ["CUE"], "PSP": []}
                for plat, subfolders in REQUIRED_STRUCTURE.items():
                    plat_path = os.path.join(REDUMP_DIR, plat)
                    os.makedirs(plat_path, exist_ok=True)
                    for sub in subfolders:
                        os.makedirs(os.path.join(plat_path, sub), exist_ok=True)

                delay = 0.01 if Quick_TIME else 1.0
                self.set_timer(delay, run_dirs_verification_automatic)
            else:
                self.add_log("[yellow]⚠ No DAT records found in database. Download required.[/yellow]")
                chk_dat.text = "2. Download and parse DAT files"
                chk_dat.value = False
                chk_dat.disabled = False

        def run_database_verification():
            self.add_log("Performing database verification...")
            is_valid, error_msg = RC_Oper_DB_Check()
            
            if is_valid:
                self.add_log("[green]✔ RomConvert.DB is present and schema is valid.[/green]")
                chk_db.text = "1. Database verification"
                chk_db.value = True
                chk_db.disabled = True
                
                self.add_log("Running pre-flight check for DAT files...")
                delay = 0.01 if Quick_TIME else 1.0
                self.set_timer(delay, run_dat_verification)
            else:
                if os.path.exists(DB_NAME):
                    self.add_log(f"[red]CRITICAL ERROR:[/red] {error_msg}")
                    self.add_log("[red]Database file is corrupted or outdated! Action required.[/red]")
                    chk_db.text = "1. Fix Corrupted Database (RomConvert.DB) [DATA LOSS]"
                else:
                    self.add_log("[yellow]⚠ RomConvert.DB not found. Creation required.[/yellow]")
                    chk_db.text = "1. Create Database file (RomConvert.DB)"
                
                chk_db.value = False
                chk_db.disabled = False
                chk_dat.disabled = True

        def initialize_ui():
            self.print_startup_logs()
            self.add_log("Running pre-flight checks...")
            delay = 0.01 if Quick_TIME else 1.0
            self.set_timer(delay, run_database_verification)

        self.call_after_refresh(initialize_ui)

    def evaluate_step_4_on_startup(self) -> None:
        scenario = self.evaluate_cue_sbi_scenarios()
        chk_cue_sbi = self.query_one("#chk_cue_sbi", CheckRow)

        if scenario == 1:
            self.add_log("[green]✔ CUE/SBI files are consistent.[/green]")
            delay = 0.01 if Quick_TIME else 1.0
            self.set_timer(delay, self.run_final_verification)

        elif scenario == 2:
            self.add_log("[red]Data discrepancy (mismatch between expected and found files), new download required.[/red]")
            chk_cue_sbi.text = "4. Download CUE/SBI files"
            chk_cue_sbi.disabled = False
            self.add_log("[yellow]⚠ Requirement unlocked: You can now download CUE/SBI files.[/yellow]")

        elif scenario == 3:
            self.add_log("[yellow]Necessary ZIP files missing in Redump directory. Download required.[/yellow]")
            chk_cue_sbi.text = "4. Download CUE/SBI files"
            chk_cue_sbi.disabled = False
            self.add_log("[yellow]⚠ Requirement unlocked: You can now download CUE/SBI files.[/yellow]")

        elif scenario == 4:
            self.add_log("[yellow]Some folders are empty. Download required.[/yellow]")
            chk_cue_sbi.text = "4. Download CUE/SBI files"
            chk_cue_sbi.disabled = False
            self.add_log("[yellow]⚠ Requirement unlocked: You can now download CUE/SBI files.[/yellow]")

    @work(thread=True)
    def process_dat_step(self, check_row: CheckRow):
        self.add_log("[yellow]⚙ Connecting to Redump and downloading DAT files... please wait...[/yellow]", persistent=False)
        download_results = RC_Oper_Smart_Download("DAT", TEMPOR_DIR, REDUMP_DIR)
        
        self.clear_transient_log()
        for sys_name, (success, msg) in download_results.items():
            if success:
                self.add_log(f"  [green]✔ {sys_name}: {msg}[/green]")
            else:
                self.add_log(f"  [red]✖ {sys_name}: {msg}[/red]")

        self.add_log("[yellow]⚙ Extracting ZIP files and populating Database... please be patient...[/yellow]", persistent=False)
        parse_results = RC_Oper_DAT_Parse_And_Populate(DB_NAME, REDUMP_DIR)
        stats = RC_Oper_DAT_Get_Stats(DB_NAME)
        
        def update_ui_post_download():
            self.clear_transient_log()
            if parse_results["success"]:
                self.add_log("[green]✔ DAT files successfully extracted and parsed into the database.[/green]")
                for sys_name, data in stats.items():
                    if data["records"] > 0:
                        self.add_log(f"  - {sys_name}: {data['records']:>6,} records over {data['discs']:>6,} discs")
                
                check_row.disabled = True
                check_row.text = "2. DAT files verified"
                
                chk_dirs = self.query_one("#chk_dirs", CheckRow)
                REQUIRED_STRUCTURE = {"PSX": ["CUE", "SBI"], "PS2": ["CUE"], "PSP": []}
                for plat, subfolders in REQUIRED_STRUCTURE.items():
                    plat_path = os.path.join(REDUMP_DIR, plat)
                    os.makedirs(plat_path, exist_ok=True)
                    for sub in subfolders:
                        os.makedirs(os.path.join(plat_path, sub), exist_ok=True)
                chk_dirs.text = "3. CUE/SBI directory structure verified"
                chk_dirs.value = True
                chk_dirs.disabled = True
                
                delay = 0.01 if Quick_TIME else 1.0
                self.set_timer(delay, self.evaluate_step_4_on_startup)
            else:
                self.add_log(f"[red]✖ Error during extraction and parsing: {parse_results['error']}[/red]")
                check_row.value = False
            
        self.call_from_thread(update_ui_post_download)

    def process_dirs_step(self, check_row: CheckRow):
        self.clear_transient_log()
        
        REQUIRED_STRUCTURE = {"PSX": ["CUE", "SBI"], "PS2": ["CUE"], "PSP": []}
        results = []
        for plat, subfolders in REQUIRED_STRUCTURE.items():
            plat_path = os.path.join(REDUMP_DIR, plat)
            os.makedirs(plat_path, exist_ok=True)
            for sub in subfolders:
                target_path = os.path.join(plat_path, sub)
                if os.path.exists(target_path):
                    status = "Already present"
                else:
                    try:
                        os.makedirs(target_path, exist_ok=True)
                        status = "Created"
                    except OSError as e:
                        status = f"Error: {e}"
                results.append((f"{plat}/{sub}", status))

        for key, status in results:
            self.add_log(f"  - {key:<10} : {status}")

        check_row.disabled = True
        check_row.text = "3. CUE/SBI directory structure verified"
        self.add_log("[green]✔ CUE/SBI directory structure successfully verified.[/green]")
        
        delay = 0.01 if Quick_TIME else 1.0
        self.set_timer(delay, self.evaluate_step_4_on_startup)

    @work(thread=True)
    def process_cue_sbi_step(self, check_row: CheckRow):
        self.add_log("[yellow]⚙ Downloading and updating CUE/SBI packages... please wait...[/yellow]", persistent=False)
        
        res_cue = RC_Oper_Smart_Download("CUE", TEMPOR_DIR, REDUMP_DIR)
        res_sbi = RC_Oper_Smart_Download("SBI", TEMPOR_DIR, REDUMP_DIR)

        self.clear_transient_log()
        for d_res in [res_cue, res_sbi]:
            for sys_name, (success, msg) in d_res.items():
                if success:
                    self.add_log(f"  [green]✔ {sys_name}: {msg}[/green]")
                else:
                    self.add_log(f"  [red]✖ {sys_name}: {msg}[/red]")

        self.add_log("[yellow]⚙ Verifying and unpacking CUE/SBI archives... please be patient...[/yellow]", persistent=False)
        
        details = self.get_detailed_zip_mapping()
        mapping = {
            "PSX/CUE": ("PSX", "CUE", "cue"),
            "PSX/SBI": ("PSX", "SBI", "sbi"),
            "PS2/CUE": ("PS2", "CUE", "cue")
        }

        for key, (plat, sub, keyword) in mapping.items():
            target_folder = os.path.join(REDUMP_DIR, plat, sub)
            os.makedirs(target_folder, exist_ok=True)
            
            current_count = len([n for n in os.listdir(target_folder) if not n.startswith('.')])
            exp_count = details[key]["expected"]

            target_zip = None
            if details[key]["zip_name"]:
                target_zip = os.path.join(REDUMP_DIR, details[key]["zip_name"])

            if current_count == 0:
                if target_zip and os.path.exists(target_zip):
                    with zipfile.ZipFile(target_zip, 'r') as zf:
                        zf.extractall(target_folder)
            elif current_count != exp_count:
                for f_item in os.listdir(target_folder):
                    f_path = os.path.join(target_folder, f_item)
                    if os.path.isfile(f_path):
                        os.remove(f_path)
                if target_zip and os.path.exists(target_zip):
                    with zipfile.ZipFile(target_zip, 'r') as zf:
                        zf.extractall(target_folder)

        def finalize_ui_cue_sbi():
            self.clear_transient_log()
            self.run_final_verification()

        self.call_from_thread(finalize_ui_cue_sbi)

    @on(CheckRow.Changed)
    def handle_checkbox(self, event: CheckRow.Changed):
        chk_id = event.check_row.id
        
        if event.value:
            if chk_id == "chk_db":
                success, msg = RC_Oper_DB_Create()
                
                if success:
                    log = self.query_one("#system_log", RichLog)
                    log.clear()
                    self.persistent_logs.clear()
                    
                    self.print_startup_logs()
                    self.add_log("[green]✔ RomConvert.DB is present and schema is valid.[/green]")
                    self.add_log(f"[green]✔ {msg}[/green]")
                    
                    event.check_row.disabled = True
                    event.check_row.text = "1. Database verification"
                    
                    has_data, stats = RC_Oper_DAT_Check_Records()
                    if has_data:
                        self.add_log("[green]✔ DAT files already present in database:[/green]")
                        for sys_name, data in stats.items():
                            if data["records"] > 0:
                                self.add_log(f"  - {sys_name}: {data['records']:>6,} records over {data['discs']:>6,} discs")
                        
                        next_chk = self.query_one("#chk_dat", CheckRow)
                        next_chk.text = "2. DAT files verified"
                        next_chk.value = True
                        next_chk.disabled = True
                        
                        dirs_chk = self.query_one("#chk_dirs", CheckRow)
                        dirs_chk.text = "3. CUE/SBI directory structure verified"
                        dirs_chk.value = True
                        dirs_chk.disabled = True
                        
                        delay = 0.01 if Quick_TIME else 1.0
                        self.set_timer(delay, self.evaluate_step_4_on_startup)
                    else:
                        next_chk = self.query_one("#chk_dat", CheckRow)
                        next_chk.text = "2. DAT files verified"
                        next_chk.value = True
                        next_chk.disabled = True
                        self.process_dat_step(next_chk)
                else:
                    self.add_log(f"[red]✖ {msg}[/red]")
                    event.check_row.value = False
                
            elif chk_id == "chk_dat":
                self.process_dat_step(event.check_row)
                
            elif chk_id == "chk_dirs":
                if Quick_TIME:
                    self.process_dirs_step(event.check_row)
                else:
                    self.set_timer(1.0, lambda: self.process_dirs_step(event.check_row))
                
            elif chk_id == "chk_cue_sbi":
                self.process_cue_sbi_step(event.check_row)


if __name__ == "__main__":
    app = RomConvertApp()
    app.run()