import os
import subprocess
import shutil
from typing import List, Tuple
from tqdm import tqdm
from colorama import Fore, Style

# Paths to binaries - try to use specific paths first, then fallback to system path
FFMPEG_PATH = "/opt/homebrew/bin/ffmpeg"
if not os.path.exists(FFMPEG_PATH):
    FFMPEG_PATH = shutil.which("ffmpeg")

EXIFTOOL_PATH = "/opt/homebrew/bin/exiftool"
if not os.path.exists(EXIFTOOL_PATH):
    EXIFTOOL_PATH = shutil.which("exiftool")

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}

def check_dependencies() -> Tuple[bool, str]:
    """Check if ffmpeg and exiftool are available."""
    missing = []
    if not FFMPEG_PATH:
        missing.append("ffmpeg")
    if not EXIFTOOL_PATH:
        missing.append("exiftool")
    
    if missing:
        return False, f"Missing dependencies: {', '.join(missing)}"
    return True, ""

def compress_video_file(input_path: str, output_path: str) -> bool:
    """
    Compress a video file using ffmpeg and copy metadata using exiftool.
    Returns True if successful, False otherwise.
    """
    if not FFMPEG_PATH or not EXIFTOOL_PATH:
        return False

    try:
        # 1. Compress with ffmpeg
        # "$FFMPEG" -i "$INPUT" -c:v libx264 -crf 22 -preset medium -c:a aac -b:a 128k -map_metadata 0 "$OUTPUT"
        ffmpeg_cmd = [
            FFMPEG_PATH,
            "-y", # Overwrite output file if exists (we check before calling this)
            "-i", input_path,
            "-c:v", "libx264",
            "-crf", "22",
            "-preset", "medium",
            "-c:a", "aac",
            "-b:a", "128k",
            "-map_metadata", "0",
            output_path
        ]
        
        # Suppress ffmpeg output unless there's an error
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"\n{Fore.RED}FFmpeg error for {input_path}:{Style.RESET_ALL}\n{result.stderr}")
            return False

        # 2. Copy metadata with exiftool
        # "$EXIFTOOL" -tagsFromFile "$INPUT" -all:all "$OUTPUT" -overwrite_original
        exiftool_cmd = [
            EXIFTOOL_PATH,
            "-tagsFromFile", input_path,
            "-all:all",
            output_path,
            "-overwrite_original"
        ]
        
        result = subprocess.run(exiftool_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"\n{Fore.RED}Exiftool error for {input_path}:{Style.RESET_ALL}\n{result.stderr}")
            # Don't fail the whole process if just metadata copy fails, but warn
            return True 

        return True

    except Exception as e:
        print(f"\n{Fore.RED}Exception processing {input_path}:{Style.RESET_ALL} {e}")
        return False

def scan_and_compress(directory: str):
    """
    Recursively scan directory for videos and compress them.
    """
    # Check dependencies first
    valid, error_msg = check_dependencies()
    if not valid:
        print(f"{Fore.RED}Error: {error_msg}{Style.RESET_ALL}")
        print("Please install ffmpeg and exiftool.")
        return

    print(f"\n{Fore.CYAN}Scanning for videos in: {directory}{Style.RESET_ALL}")
    
    videos_to_process = []
    
    # Walk through directory
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()
            
            # Skip non-video files
            if ext not in VIDEO_EXTENSIONS:
                continue
                
            # Skip already compressed files
            if file.endswith("-small.mp4"):
                continue
                
            # Check if compressed version already exists
            name_without_ext = os.path.splitext(file)[0]
            expected_output = os.path.join(root, f"{name_without_ext}-small.mp4")
            
            if os.path.exists(expected_output):
                continue
                
            videos_to_process.append((file_path, expected_output))
            
    if not videos_to_process:
        print(f"{Fore.YELLOW}No new videos found to compress.{Style.RESET_ALL}")
        return

    print(f"Found {len(videos_to_process)} videos to compress.\n")
    
    # Process videos
    success_count = 0
    fail_count = 0
    
    with tqdm(total=len(videos_to_process), unit="file", desc="Compressing", colour="green") as pbar:
        for input_path, output_path in videos_to_process:
            filename = os.path.basename(input_path)
            pbar.set_description(f"Compressing: {filename}")
            
            if compress_video_file(input_path, output_path):
                success_count += 1
            else:
                fail_count += 1
                
            pbar.update(1)
            
    print(f"\n{Fore.GREEN}Done!{Style.RESET_ALL}")
    print(f"Successfully compressed: {success_count}")
    if fail_count > 0:
        print(f"{Fore.RED}Failed: {fail_count}{Style.RESET_ALL}")
    
    # Notify user (macOS only)
    try:
        subprocess.run([
            "osascript", "-e", 
            f'display notification "Сжато {success_count} видео" with title "Video Compressor"'
        ])
    except:
        pass
