import os
import subprocess
import shutil
import re
from typing import List, Tuple, Optional
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

def get_video_duration(file_path: str) -> Optional[float]:
    """Get video duration in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except:
        pass
    return None

def parse_time_to_seconds(time_str: str) -> float:
    """Parse ffmpeg time string (HH:MM:SS.mm) to seconds."""
    try:
        h, m, s = time_str.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    except:
        return 0.0

def compress_video_file(input_path: str, output_path: str, pbar: Optional[tqdm] = None) -> bool:
    """
    Compress a video file using ffmpeg and copy metadata using exiftool.
    Updates the provided progress bar if given.
    Returns True if successful, False otherwise.
    """
    if not FFMPEG_PATH or not EXIFTOOL_PATH:
        return False

    try:
        # 1. Compress with ffmpeg
        # Added -pix_fmt yuv420p for better compatibility (QuickTime etc)
        # Added -progress pipe:1 to get progress info on stdout
        ffmpeg_cmd = [
            FFMPEG_PATH,
            "-y", # Overwrite output file if exists
            "-i", input_path,
            "-c:v", "libx264",
            "-crf", "22",
            "-preset", "medium",
            "-pix_fmt", "yuv420p", # Ensure compatibility
            "-c:a", "aac",
            "-b:a", "128k",
            "-map_metadata", "0",
            output_path
        ]
        
        # Run ffmpeg with Popen to capture stderr for progress
        # ffmpeg outputs progress to stderr by default
        process = subprocess.Popen(
            ffmpeg_cmd,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Regex to extract time from ffmpeg output: time=00:00:05.20
        time_pattern = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})")
        
        last_time = 0.0
        
        # Read stderr line by line
        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break
            
            if line and pbar:
                match = time_pattern.search(line)
                if match:
                    current_time_str = match.group(1)
                    current_seconds = parse_time_to_seconds(current_time_str)
                    
                    # Update progress bar with the difference
                    increment = current_seconds - last_time
                    if increment > 0:
                        pbar.update(increment)
                        last_time = current_seconds

        if process.returncode != 0:
            print(f"\n{Fore.RED}FFmpeg error for {input_path}{Style.RESET_ALL}")
            return False

        # Verify output file exists and has size
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            print(f"\n{Fore.RED}FFmpeg failed to create valid file: {output_path}{Style.RESET_ALL}")
            return False

        # 2. Copy metadata with exiftool
        exiftool_cmd = [
            EXIFTOOL_PATH,
            "-tagsFromFile", input_path,
            "-all:all",
            output_path,
            "-overwrite_original"
        ]
        
        result = subprocess.run(exiftool_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"\n{Fore.YELLOW}Exiftool warning for {input_path}:{Style.RESET_ALL}")
            print(result.stderr)
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                 print(f"\n{Fore.RED}Exiftool corrupted the file: {output_path}{Style.RESET_ALL}")
                 return False
            return True 

        return True

    except Exception as e:
        print(f"\n{Fore.RED}Exception processing {input_path}:{Style.RESET_ALL} {e}")
        # Try to cleanup bad output
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
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

    total_files = len(videos_to_process)
    print(f"Found {total_files} videos to compress.\n")
    
    # Process videos
    success_count = 0
    fail_count = 0
    
    for idx, (input_path, output_path) in enumerate(videos_to_process, 1):
        filename = os.path.basename(input_path)
        
        # Get duration for progress bar
        duration = get_video_duration(input_path)
        if not duration:
            duration = 100 # Fallback if duration unknown
            
        # Create progress bar for this file
        # Format: Compressing: filename: 20%|...| 8/40 [time, rate]
        bar_format = (
            f'{Fore.CYAN}{{desc}}{Style.RESET_ALL}: '
            f'{Fore.GREEN}{{percentage:3.0f}}%{Style.RESET_ALL} '
            f'|{{bar}}| '
            f'{Fore.YELLOW}{idx}/{total_files}{Style.RESET_ALL} '
            f'[{Fore.MAGENTA}{{elapsed}}<{{remaining}}{Style.RESET_ALL}, {{rate_fmt}}]'
        )
        
        with tqdm(total=duration, 
                  unit='s', 
                  desc=f"Compressing: {filename}",
                  bar_format=bar_format,
                  colour='green') as pbar:
            
            if compress_video_file(input_path, output_path, pbar):
                success_count += 1
            else:
                fail_count += 1
            
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
