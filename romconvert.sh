#!/bin/bash

if [ "$#" -lt 2 ]; then
    echo "Errore: parametri mancanti."
    echo "Sintassi: romconvert <sistema> <file_archivio...>"
    echo "Esempio:  romconvert psx \"Final Fantasy VII*.7z\""
    echo "Esempio:  romconvert ps2 \"Metal Gear Solid 2*.zip\""
    exit 1
fi

# 1. Configurazione percorsi
SISTEMA=$1
DEST_DIR="/mnt/d/ES-DE/ROMs/$SISTEMA"
CUE_DIR="/mnt/d/romvault/Extra Utilities/1- Cue library per i Bin PSX"

shift
NUM_DISCHI=$#

SECONDS=0
echo "Sistema di destinazione: $SISTEMA ($DEST_DIR)"
echo "Rilevati $NUM_DISCHI file da processare."
echo "========================================"

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

if [ "$NUM_DISCHI" -eq 1 ]; then
    # --- LOGICA MONODISCO ---
    NOME_FILE=$(basename "$1")
    NOME_GIOCO="${NOME_FILE%.*}"
    echo "Modalità MONODISCO per: $NOME_GIOCO"
    
    TEMP_EXTRACT="temp_$NOME_GIOCO"
    rm -rf "$TEMP_EXTRACT"
    mkdir -p "$TEMP_EXTRACT"
    
    echo -n "Estrazione archivio... "
    if 7z x "$1" -o"$TEMP_EXTRACT" -y > /dev/null 2>&1; then
        echo "Fatto!"
    else
        echo "ERRORE nell'estrazione dell'archivio (file corrotto o inesistente)."
        rm -rf "$TEMP_EXTRACT"
        exit 1
    fi
    
    FILE_INDICE=$(find "$TEMP_EXTRACT" -maxdepth 1 -type f \( -iname "*.cue" -o -iname "*.ccd" -o -iname "*.iso" \) | head -n 1)
    
    if [ -z "$FILE_INDICE" ]; then
        ricerca_cue_mancante "$TEMP_EXTRACT"
        FILE_INDICE=$(find "$TEMP_EXTRACT" -maxdepth 1 -type f \( -iname "*.cue" -o -iname "*.ccd" -o -iname "*.iso" \) | head -n 1)
    fi
    
    if [ -n "$FILE_INDICE" ]; then
        if [[ "${FILE_INDICE,,}" == *.iso ]]; then
            CMD_CHD="createdvd"
        else
            CMD_CHD="createcd"
        fi
        
        echo -n "Compressione in CHD (può richiedere qualche minuto)... "
        if chdman $CMD_CHD -f -i "$FILE_INDICE" -o "$DEST_DIR/$NOME_GIOCO.chd" > /dev/null 2>&1; then
            echo "Fatto!"
            echo "File generato: $DEST_DIR/$NOME_GIOCO.chd"
        else
            echo "ERRORE durante la creazione del CHD con chdman."
        fi
    else
        echo "Errore: Impossibile procedere. Nessun .cue/iso trovabile per $NOME_GIOCO."
    fi
    
    rm -rf "$TEMP_EXTRACT"

else
    # --- LOGICA MULTIDISCO (M3U) ---
    PRIMO_FILE_FULL=$(basename "$1")
    PRIMO_FILE="${PRIMO_FILE_FULL%.*}"
    NOME_BASE=$(echo "$PRIMO_FILE" | sed -E 's/ ?\((disc|disk|disco|cd|dvd)[^)]*\)//gi')
    
    echo "Modalità MULTIDISCO per: $NOME_BASE"
    
    DIR_MULTIDISCO="$DEST_DIR/.multidisco"
    CARTELLA_GIOCO="$DIR_MULTIDISCO/$NOME_BASE"
    FILE_M3U="$DEST_DIR/$NOME_BASE.m3u"

    mkdir -p "$CARTELLA_GIOCO"
    > "$FILE_M3U"

    for archivio in "$@"; do
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
            if [[ "${FILE_INDICE,,}" == *.iso ]]; then
                CMD_CHD="createdvd"
            else
                CMD_CHD="createcd"
            fi
            
            echo -n "   Compressione in CHD... "
            if chdman $CMD_CHD -f -i "$FILE_INDICE" -o "$CARTELLA_GIOCO/$NOME_FILE_ATTUALE.chd" > /dev/null 2>&1; then
                echo "Fatto!"
                echo ".multidisco/$NOME_BASE/$NOME_FILE_ATTUALE.chd" >> "$FILE_M3U"
            else
                echo "ERRORE durante la creazione del CHD."
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
