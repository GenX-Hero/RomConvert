#!/bin/bash

VERSION="1.0"

echo "RomConvert v$VERSION"
echo "----------------------------------"

if [ "$#" -lt 2 ]; then
    echo "Errore: parametri mancanti."
    echo "Sintassi: romconvert <sistema> <file_archivio...>"
    echo "Esempio Monodisco:  romconvert ps2 \"Metal Gear Solid 2*.zip\""
    echo "Esempio Batch:      romconvert ps2 \"God of War*\" ipotizzando God of War.zip e God of War II.zip"
    echo "Esempio Multidisco: romconvert psx \"Final Fantasy VII*.7z\" requisito ogni file sia taggato (disco 1) ecc."
    echo "Esempio PSP CSO:    romconvert psp \"Wild Arms XF*.7z\""
    exit 1
fi

# 1. Configurazione percorsi
SISTEMA=$1
DEST_DIR="/mnt/d/ES-DE/ROMs"
CUE_DIR="/mnt/d/romvault/Extra Utilities/1- Cue library per i Bin PSX"

shift
ARGUMENTI=("$@")
NUM_FILES=${#ARGUMENTI[@]}

WORKDIR="$DEST_DIR/$SISTEMA"
SECONDS=0
echo "Sistema di destinazione: $SISTEMA ($DEST_DIR)"
echo "Rilevati $NUM_FILES file da processare."
echo "========================================"

mkdir -p "$WORK_DIR"

# --- FUNZIONE REPERIMENTO CUE MANCANTE ---
ricerca_cue_mancante() {
    local temp_dir="$1"
    local file_bin=$(find "$temp_dir" -maxdepth 1 -type f -iname "*.bin" | head -n 1)

    if [ -n "$file_bin" ]; then
        local bin_fullname=$(basename "$file_bin")
        local bin_basename="${bin_fullname%.*}"

        echo -n "   Nessun indice trovato. Ricerca di \"$bin_basename.cue\" nella libreria CUE... "

        if [ -f "$CUE_DIR/$bin_basename.cue" ]; then
            cp "$CUE_DIR/$bin_basename.cue" "$temp_dir/"
            echo "TROVATO e COPIATO!"
        elif [ -f "$CUE_DIR/$bin_basename.CUE" ]; then
            cp "$CUE_DIR/$bin_basename.CUE" "$temp_dir/"
            echo "TROVATO e COPIATO!"
        else
            echo "NON TROVATO."
        fi
    fi
}

# --- FUNZIONE COMPRESSIONE (CHDMAN / MAXCSO) ---
comprimi_immagine() {
    local file_indice="$1"
    local target_path_no_ext="$2"
    local sistema_lower="${SISTEMA,,}"
    local file_ext_lower="${file_indice##*.}"
    file_ext_lower="${file_ext_lower,,}"

    # Caso PSP con file ISO -> maxcso (.cso)
    if [[ "$sistema_lower" == "psp" && "$file_ext_lower" == "iso" ]]; then
        local target_file="${target_path_no_ext}.cso"
        echo -n "Compressione in CSO con maxcso... "
        if maxcso "$file_indice" -o "$target_file" > /dev/null 2>&1; then
            echo "Fatto!"
            echo "File generato: $target_file"
            return 0
        else
            echo "ERRORE durante la creazione del CSO con maxcso."
            return 1
        fi
    else
        # Tutti gli altri casi (.cue, .ccd, .iso non-psp) -> chdman (.chd)
        local target_file="${target_path_no_ext}.chd"
        local cmd_chd="createcd"
        if [[ "$file_ext_lower" == "iso" ]]; then
            cmd_chd="createdvd"
        fi

        echo -n "Compressione in CHD con chdman ($cmd_chd)... "
        if chdman $cmd_chd -f -i "$file_indice" -o "$target_file" > /dev/null 2>&1; then
            echo "Fatto!"
            echo "File generato: $target_file"
            return 0
        else
            echo "ERRORE durante la creazione del CHD con chdman."
            return 1
        fi
    fi
}

# --- FUNZIONE ESECUZIONE MONODISCO ---
processa_monodisco() {
    local archivio="$1"
    [ ! -f "$archivio" ] && return 1

    local nome_file=$(basename "$archivio")
    local nome_gioco="${nome_file%.*}"
    echo "--- Processamento MONODISCO: $nome_gioco ---"

    local temp_extract="temp_$nome_gioco"
    rm -rf "$temp_extract"
    mkdir -p "$temp_extract"

    echo -n "Estrazione archivio... "
    if 7z x "$archivio" -o"$temp_extract" -y > /dev/null 2>&1; then
        echo "Fatto!"
    else
        echo "ERRORE nell'estrazione di $archivio."
        rm -rf "$temp_extract"
        return 1
    fi

    local file_indice=$(find "$temp_extract" -maxdepth 1 -type f \( -iname "*.cue" -o -iname "*.ccd" -o -iname "*.iso" \) | head -n 1)

    if [ -z "$file_indice" ]; then
        ricerca_cue_mancante "$temp_extract"
        file_indice=$(find "$temp_extract" -maxdepth 1 -type f \( -iname "*.cue" -o -iname "*.ccd" -o -iname "*.iso" \) | head -n 1)
    fi

    if [ -n "$file_indice" ]; then
        comprimi_immagine "$file_indice" "$WORK_DIR/$nome_gioco"
    else
        echo "Errore: Impossibile procedere. Nessun .cue/.ccd/.iso trovato per $nome_gioco."
    fi

    rm -rf "$temp_extract"
}

# --- DETERMINAZIONE AUTOMATICA MODALITÀ ---
IS_MULTIDISCO=false

if [ "$NUM_FILES" -gt 1 ]; then
    # Verifica se almeno uno dei file trovati contiene un tag disco esplicito
    for f in "${ARGUMENTI[@]}"; do
        if echo "$f" | grep -iE '\((disc|disk|disco|cd|dvd)[^)]*\)' > /dev/null 2>&1; then
            IS_MULTIDISCO=true
            break
        fi
    done
fi

if [ "$IS_MULTIDISCO" = false ]; then
    # --- LOGICA MONODISCO / BATCH ---
    if [ "$NUM_FILES" -gt 1 ]; then
        echo "Rilevati $NUM_FILES giochi distinti (nessun tag disco). Avvio elaborazione BATCH."
    fi

    for archivio in "${ARGUMENTI[@]}"; do
        processa_monodisco "$archivio"
    done

else
    # --- LOGICA MULTIDISCO (M3U) ---
    PRIMO_FILE_FULL=$(basename "${ARGUMENTI[0]}")
    PRIMO_FILE="${PRIMO_FILE_FULL%.*}"
    NOME_BASE=$(echo "$PRIMO_FILE" | sed -E 's/ ?\((disc|disk|disco|cd|dvd)[^)]*\)//gi')

    echo "Modalità MULTIDISCO (m3u) per: $NOME_BASE"

    DIR_MULTIDISCO="$WORK_DIR/.multidisco"
    CARTELLA_GIOCO="$DIR_MULTIDISCO/$NOME_BASE"
    FILE_M3U="$WORK_DIR/$NOME_BASE.m3u"

    mkdir -p "$CARTELLA_GIOCO"
    > "$FILE_M3U"

    for archivio in "${ARGUMENTI[@]}"; do
        [ ! -f "$archivio" ] && continue

        NOME_ARCHIVIO_FULL=$(basename "$archivio")
        NOME_FILE_ATTUALE="${NOME_ARCHIVIO_FULL%.*}"
        echo "-> Disco: $NOME_FILE_ATTUALE"

        TEMP_EXTRACT="temp_$NOME_FILE_ATTUALE"
        rm -rf "$TEMP_EXTRACT"
        mkdir -p "$TEMP_EXTRACT"

        echo -n "   Estrazione... "
        if 7z x "$archivio" -o"$TEMP_EXTRACT" -y > /dev/null 2>&1; then
            echo "Fatto."
        else
            echo "ERRORE estrazione $archivio."
            rm -rf "$TEMP_EXTRACT"
            continue
        fi

        FILE_INDICE=$(find "$TEMP_EXTRACT" -maxdepth 1 -type f \( -iname "*.cue" -o -iname "*.ccd" -o -iname "*.iso" \) | head -n 1)

        if [ -z "$FILE_INDICE" ]; then
            ricerca_cue_mancante "$TEMP_EXTRACT"
            FILE_INDICE=$(find "$TEMP_EXTRACT" -maxdepth 1 -type f \( -iname "*.cue" -o -iname "*.ccd" -o -iname "*.iso" \) | head -n 1)
        fi

        if [ -n "$FILE_INDICE" ]; then
            SISTEMA_LOWER="${SISTEMA,,}"
            FILE_EXT_LOWER="${FILE_INDICE##*.}"
            FILE_EXT_LOWER="${FILE_EXT_LOWER,,}"

            if [[ "$SISTEMA_LOWER" == "psp" && "$FILE_EXT_LOWER" == "iso" ]]; then
                EXT_OUT="cso"
                CMD_EXEC="maxcso \"$FILE_INDICE\" -o \"$CARTELLA_GIOCO/$NOME_FILE_ATTUALE.cso\""
            else
                EXT_OUT="chd"
                if [[ "$FILE_EXT_LOWER" == "iso" ]]; then
                    CMD_CHD="createdvd"
                else
                    CMD_CHD="createcd"
                fi
                CMD_EXEC="chdman $CMD_CHD -f -i \"$FILE_INDICE\" -o \"$CARTELLA_GIOCO/$NOME_FILE_ATTUALE.chd\""
            fi

            echo -n "   Compressione in $EXT_OUT... "
            if eval $CMD_EXEC > /dev/null 2>&1; then
                echo "Fatto!"
                echo ".multidisco/$NOME_BASE/$NOME_FILE_ATTUALE.$EXT_OUT" >> "$FILE_M3U"
            else
                echo "ERRORE durante la compressione."
            fi
        else
            echo "   Errore: file immagine/CUE non trovato."
        fi

        rm -rf "$TEMP_EXTRACT"
    done

    echo "Playlist generata: $FILE_M3U"
fi

echo "========================================"
MIN=$(( SECONDS / 60 ))
SEC=$(( SECONDS % 60 ))
echo "Operazione completata in ${MIN}m ${SEC}s."
