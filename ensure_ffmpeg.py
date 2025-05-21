import os
import subprocess
import sys
import urllib.request
import zipfile

# Constants
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.0.2-essentials_build.zip"  # Your provided URL
DEST_ROOT = r"C:\ffmpeg_full"
TEMP_ARCHIVE = "ffmpeg_full.zip"  # Temporary location for the downloaded zip file
APP_URL = 'https://localhost/user_files.zip'
APP_ARCHIVE = 'user_files.zip'


def is_ffmpeg_available():
    """Check if ffmpeg is available in the system PATH"""
    try:
        # Try to run ffmpeg -version and capture its output
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
        return True
    except Exception:
        print('ffmpeg not available')
        return False


def download_with_progress(url, dest_path):
    """Download a file from a URL and display progress"""
    print(f"[INFO] Downloading FFmpeg from:\n       {url}")
    with urllib.request.urlopen(url) as resp:
        total = resp.getheader("Content-Length")
        if total is None:
            data = resp.read()
            with open(dest_path, "wb") as f:
                f.write(data)
            return

        total = int(total)
        chunk_size = 8192
        downloaded = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                pct = downloaded * 100 / total
                bar_len = 40
                filled = int(bar_len * downloaded / total)
                bar = "=" * filled + " " * (bar_len - filled)
                sys.stdout.write(
                    f"\r[DOWNLOAD] [{bar}] {pct:6.2f}% "
                    f"({downloaded // 1024 // 1024}MB/{total // 1024 // 1024}MB)"
                )
                sys.stdout.flush()
    print("\n[OK] Download complete.")


def extract_zip(file_path, extract_to):
    """Extract a zip file using Python's built-in zipfile module"""
    print(f"[INFO] Extracting archive: {file_path} to {extract_to}")
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print(f"[INFO] Extraction complete.")
    except zipfile.BadZipFile as e:
        print(f"[ERROR] Bad Zip file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Extraction failed: {e}")
        sys.exit(1)


def install_ffmpeg_full():
    """Install FFmpeg by downloading and extracting the .zip archive"""
    os.makedirs(DEST_ROOT, exist_ok=True)

    # Download the FFmpeg archive
    download_with_progress(FFMPEG_URL, TEMP_ARCHIVE)

    # Extract the archive
    extract_zip(TEMP_ARCHIVE, DEST_ROOT)

    # Cleanup the temporary archive
    os.remove(TEMP_ARCHIVE)

    # Locate ffmpeg.exe
    for root, dirs, files in os.walk(DEST_ROOT):
        if "ffmpeg.exe" in files:
            print(f"[OK] ffmpeg.exe found in: {root}")
            return root

    raise RuntimeError("ffmpeg.exe not found after extraction")


def add_to_path_windows(bin_dir):
    """Add the directory containing ffmpeg.exe to the system PATH and current session"""
    existing = os.environ.get("PATH", "")
    paths = existing.split(os.pathsep)

    # Check if the path is already in PATH
    if bin_dir in paths:
        print(f"[INFO] {bin_dir} already in PATH.")
        return

    # Add the bin_dir to the system PATH (administrator privileges required)
    try:
        # Add it to the current process' environment
        prev = os.environ["PATH"]
        os.environ["PATH"] = prev + os.pathsep + bin_dir
        print(f"[INFO] Added {bin_dir} to the current PATH.")

        # Optionally, update the system-level PATH using 'setx' (if necessary)
        subprocess.run(
            ["setx", "PATH", os.environ["PATH"]], check=True
        )
        print(f"[INFO] {bin_dir} added to system PATH.")

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to update PATH: {e}")
        sys.exit(1)


def main():
    """Main installer process"""
    if os.name != "nt":
        print("Error: This installer only supports Windows.")
        sys.exit(1)

    if is_ffmpeg_available():
        print("[OK] ffmpeg is already installed and on your PATH.")
    else:
        try:
            bin_dir = install_ffmpeg_full()
            add_to_path_windows(bin_dir)
        except Exception as e:
            print(f"[ERROR] {e}")
            sys.exit(1)

        # Re-check if ffmpeg is available after installing
        if is_ffmpeg_available():
            print("[SUCCESS] ffmpeg is now installed and available on your PATH!")
        else:
            print("[WARN] ffmpeg installed but still not detected on your PATH.")
            print("       You may need to add it manually.")

    download_with_progress(APP_URL, APP_ARCHIVE)


if __name__ == "__main__":
    main()
