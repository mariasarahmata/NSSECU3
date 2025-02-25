import os
import subprocess
import json
import pandas as pd
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TOOLS_DIR = os.path.join(SCRIPT_DIR, "tools")
PHOTOREC_DIR = os.path.join(TOOLS_DIR, "testdisk-7.3-WIP")
EXIFTOOL_DIR = os.path.join(SCRIPT_DIR, "tools", "exiftool-13.19_64")
AMCACHE_DIR = os.path.join(TOOLS_DIR, "AmcacheParser")

def find_executable(tool_folder, tool_name):
    for file in os.listdir(tool_folder):
        if tool_name.lower() in file.lower() and file.endswith(".exe"):
            return os.path.join(tool_folder, file)
    return None

PHOTOREC_PATH = find_executable(PHOTOREC_DIR, "photorec")
EXIFTOOL_PATH = find_executable(EXIFTOOL_DIR, "exiftool")
AMCACHE_PARSER_PATH = find_executable(AMCACHE_DIR, "AmcacheParser")


RECOVERED_ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "RecoveredFiles"))
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RECOVERED_DIR = os.path.join(RECOVERED_ROOT_DIR, f"Recovery_{TIMESTAMP}")

BASE_DIR = os.path.join(SCRIPT_DIR, f"ForensicSession_{TIMESTAMP}")
AMCACHE_OUTPUT_DIR = os.path.join(BASE_DIR, "AmcacheAnalysis")

for directory in [BASE_DIR, AMCACHE_OUTPUT_DIR, RECOVERED_DIR]:
    os.makedirs(directory, exist_ok=True)

EXIF_OUTPUT_FILE = os.path.join(BASE_DIR, "metadata.json")

DISK_NUMBER = "1"  
DISK_PATH = f"E:\\"  
FILE_TYPES = ["jpg", "mp4"]  

def enable_file_types():
    """Configures PhotoRec to recover only selected file types."""
    print(f"\n🔍 [PhotoRec] Enabling file types: {FILE_TYPES}...")

    disable_cmd = [PHOTOREC_PATH, "/cmd", DISK_PATH, "fileopt", "disable"]
    subprocess.run(disable_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    for ftype in FILE_TYPES:
        enable_cmd = [PHOTOREC_PATH, "/cmd", DISK_PATH, "fileopt", "enable", ftype]
        subprocess.run(enable_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    print("\n✅ [PhotoRec] File type filtering applied successfully!")

def run_photorec():
    """Runs PhotoRec in CLI mode for full disk recovery."""
    if not PHOTOREC_PATH:
        print("\n[!] PhotoRec executable not found! Skipping recovery...")
        return False

    print("\n🔍 [PhotoRec] Starting controlled file recovery...")

    enable_file_types() 

    photorec_cmd = [
        PHOTOREC_PATH,  
        "/d", RECOVERED_DIR, 
        "/cmd", DISK_PATH, "search"
    ]

    result = subprocess.run(photorec_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        print(f"\n❌ [PhotoRec] Recovery failed:\n", result.stderr)
        return False

    print("\n✅ [PhotoRec] Recovery process completed successfully!")
    return True

def run_exiftool(exiftool_path, root_dir, output_file):
    if not exiftool_path or not os.path.exists(root_dir):
        print("\n[!] ExifTool skipped: Root directory not found.")
        return []

    scan_dirs = []
    for dirpath, _, filenames in os.walk(root_dir):
        if any(f.endswith((".jpg", ".pdf")) for f in filenames):  
            scan_dirs.append(dirpath)

    if not scan_dirs:
        print("\n[!] ExifTool skipped: No JPG or PDF files found in RecoveredFiles or its subdirectories.")
        return []

    print("\n🔍 [ExifTool] Extracting metadata from recovered files...")

    exif_cmd = [exiftool_path, "-r", "-json", "-ext", "jpg", "-ext", "pdf"] + scan_dirs 
    result = subprocess.run(exif_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

    if result.stdout is None or not result.stdout.strip():
        print("\n❌ [ExifTool] Encountered an error:", result.stderr)
        return []

    try:
        metadata = json.loads(result.stdout)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)
        print(f"\n✅ [ExifTool] Metadata saved at: {output_file}")
        return metadata
    except json.JSONDecodeError:
        print("\n❌ [ExifTool] Error parsing metadata JSON.")
        return []

def run_amcache_parser(amcache_parser_path, output_dir):
    if not amcache_parser_path:
        print("\n[!] AmcacheParser not found! Skipping execution history extraction...")
        return {}
    print("\n🔍 [AmcacheParser] Extracting execution history...")
    existing_csvs = set(f for f in os.listdir(output_dir) if f.endswith(".csv"))
    amcache_hve = r"C:\Windows\AppCompat\Programs\Amcache.hve"
    if not os.path.exists(amcache_hve):
        print("\n❌ [AmcacheParser] Amcache.hve not found! Skipping analysis...")
        return {}
    amcache_cmd = [amcache_parser_path, "-f", amcache_hve, "--csv", output_dir]
    result = subprocess.run(amcache_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print("\n❌ [AmcacheParser] Failed:\n", result.stderr)
        return {}
    new_csvs = set(f for f in os.listdir(output_dir) if f.endswith(".csv")) - existing_csvs
    file_count = len(new_csvs)
    if file_count == 0:
        print("\n❌ [AmcacheParser] No new data extracted.")
        return {}
    print(f"\n✅ [AmcacheParser] {file_count} CSV files generated. Output directory: {output_dir}")
    return {csv_file: os.path.join(output_dir, csv_file) for csv_file in new_csvs}


def merge_artifacts_to_csv(exif_metadata, forensic_session_dir):
    print("\n🔍 [Processing] Merging extracted forensic artifacts...")

    amcache_dir = os.path.join(forensic_session_dir, "AmcacheAnalysis")
    output_csv = os.path.join(forensic_session_dir, "consolidated_artifacts.csv")

    all_dataframes = []

    if exif_metadata:
        exif_df = pd.json_normalize(exif_metadata)
        if not exif_df.empty:
            exif_df.insert(0, "Source", "ExifTool")  # Mark as ExifTool data
            exif_df.insert(1, "Original_File", exif_df["SourceFile"])  # Store filename
            exif_df.drop(columns=["SourceFile"], inplace=True)  # Remove duplicate column
            all_dataframes.append(exif_df)
        else:
            print("❌ [ExifTool] No metadata found.")

    if os.path.exists(amcache_dir):
        amcache_files = [os.path.join(amcache_dir, f) for f in os.listdir(amcache_dir) if f.endswith(".csv")]

        for file_path in amcache_files:
            amcache_df = pd.read_csv(file_path, encoding="utf-8", encoding_errors="ignore")
            
            if not amcache_df.empty:
                amcache_df.insert(0, "Source", "Amcache")  # Mark as Amcache data
                amcache_df.insert(1, "Original_File", os.path.basename(file_path))  
                all_dataframes.append(amcache_df)
        
        print(f"\n✅ [Processing] {len(amcache_files)} Amcache CSV files found.")


    if all_dataframes:
        final_df = pd.concat(all_dataframes, ignore_index=True, sort=False)

        final_df = final_df.fillna("NaN")

        final_df.to_csv(output_csv, index=False, encoding="utf-8")

        print(f"\n✅ [Processing] Consolidated artifacts saved at: {output_csv}")

def main():
    print("\n🚀 Starting forensic analysis workflow...\n")
    run_photorec()
    metadata = run_exiftool(EXIFTOOL_PATH, RECOVERED_ROOT_DIR, EXIF_OUTPUT_FILE)
    run_amcache_parser(AMCACHE_PARSER_PATH, AMCACHE_OUTPUT_DIR)
    merge_artifacts_to_csv(metadata, BASE_DIR)
    print("\n🎯 Forensic analysis complete!")

if __name__ == "__main__":
    main()

