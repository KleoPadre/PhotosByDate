"""
Модуль для чтения метаданных из фото и видео файлов.
Извлекает дату создания из EXIF (фото) и метаданных (видео).
Использует exiftool через subprocess для максимальной совместимости.
"""

import os
import subprocess
import json
from datetime import datetime
from typing import Optional
import logging

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from pillow_heif import register_heif_opener
    if PIL_AVAILABLE:
        register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False


logger = logging.getLogger("media_organizer")


# Поддерживаемые расширения
PHOTO_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.heic', '.heif', '.cr2', '.nef', 
    '.arw', '.dng', '.raw', '.gif', '.tiff', '.tif', '.bmp', '.webp'
}

VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', 
    '.m4v', '.3gp', '.mpeg', '.mpg', '.webm', '.mts'
}


def is_media_file(filename: str) -> bool:
    """
    Проверяет, является ли файл медиа файлом.
    
    Args:
        filename: Имя файла
        
    Returns:
        True, если файл - фото или видео
    """
    ext = os.path.splitext(filename)[1].lower()
    return ext in PHOTO_EXTENSIONS or ext in VIDEO_EXTENSIONS


def is_photo(filename: str) -> bool:
    """Проверяет, является ли файл фотографией."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in PHOTO_EXTENSIONS


def is_video(filename: str) -> bool:
    """Проверяет, является ли файл видео."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in VIDEO_EXTENSIONS


def find_exiftool() -> Optional[str]:
    """
    Находит путь к exiftool.
    
    Returns:
        Путь к exiftool или None
    """
    # Возможные пути к exiftool
    possible_paths = [
        '/opt/homebrew/bin/exiftool',  # Apple Silicon Mac
        '/usr/local/bin/exiftool',      # Intel Mac / Linux
        'exiftool'                      # В PATH
    ]
    
    for path in possible_paths:
        try:
            result = subprocess.run(
                [path, '-ver'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                logger.debug(f"Найден exiftool: {path} (версия {result.stdout.strip()})")
                return path
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    
    logger.warning("exiftool не найден! Метаданные видео будут недоступны.")
    return None


# Кешируем путь к exiftool
_EXIFTOOL_PATH = None


def get_exiftool_path() -> Optional[str]:
    """Возвращает закешированный путь к exiftool."""
    global _EXIFTOOL_PATH
    if _EXIFTOOL_PATH is None:
        _EXIFTOOL_PATH = find_exiftool()
    return _EXIFTOOL_PATH


def extract_date_from_exif(file_path: str) -> Optional[datetime]:
    """
    Извлекает дату создания из EXIF фотографии.
    
    Args:
        file_path: Путь к файлу фотографии
        
    Returns:
        Объект datetime или None
    """
    if not PIL_AVAILABLE:
        logger.warning("Pillow не установлен. EXIF данные недоступны.")
        return None
    
    if not os.path.exists(file_path):
        logger.error(f"Файл не найден: {file_path}")
        return None
    
    try:
        image = Image.open(file_path)
        exif_data = image._getexif()
        
        if not exif_data:
            logger.debug(f"EXIF данные отсутствуют в файле: {file_path}")
            return None
        
        # Ищем дату создания в EXIF
        # Приоритет: DateTimeOriginal > DateTime > DateTimeDigitized
        date_tags = [36867, 306, 36868]  # DateTimeOriginal, DateTime, DateTimeDigitized
        
        for tag_id in date_tags:
            if tag_id in exif_data:
                date_str = exif_data[tag_id]
                try:
                    # Формат EXIF даты: "YYYY:MM:DD HH:MM:SS"
                    date_obj = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                    logger.debug(f"Дата из EXIF ({TAGS.get(tag_id, tag_id)}): {date_obj}")
                    return date_obj
                except ValueError as e:
                    logger.debug(f"Ошибка парсинга даты EXIF: {e}")
                    continue
        
        logger.debug(f"Дата создания не найдена в EXIF: {file_path}")
        return None
        
    except Exception as e:
        logger.debug(f"Ошибка чтения EXIF из {file_path}: {e}")
        return None


def extract_date_from_video_exiftool(file_path: str) -> Optional[datetime]:
    """
    Извлекает дату создания из метаданных видео файла используя exiftool.
    
    Args:
        file_path: Путь к видео файлу
        
    Returns:
        Объект datetime или None
    """
    exiftool_path = get_exiftool_path()
    if not exiftool_path:
        return None
    
    if not os.path.exists(file_path):
        logger.error(f"Файл не найден: {file_path}")
        return None
    
    try:
        # Запрашиваем все теги времени из видео в формате JSON
        result = subprocess.run(
            [exiftool_path, '-time:all', '-G1', '-j', '-n', file_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.debug(f"exiftool вернул ошибку для {file_path}: {result.stderr}")
            return None
        
        # Парсим JSON
        data = json.loads(result.stdout)
        if not data or len(data) == 0:
            logger.debug(f"exiftool не вернул данных для {file_path}")
            return None
        
        metadata = data[0]
        
        # Список тегов для поиска даты (в порядке приоритета)
        # Используем теги, которые мы изменяем в быстром действии
        date_tags = [
            'QuickTime:CreateDate',
            'QuickTime:MediaCreateDate',
            'QuickTime:TrackCreateDate',
            'Keys:CreationDate',
            'QuickTime:CreationDate',
        ]
        
        for tag in date_tags:
            if tag in metadata:
                date_value = metadata[tag]
                
                # Пробуем распарсить дату
                if isinstance(date_value, str):
                    try:
                        # Формат: "YYYY:MM:DD HH:MM:SS"
                        date_obj = datetime.strptime(date_value, "%Y:%m:%d %H:%M:%S")
                        logger.debug(f"Дата из видео ({tag}): {date_obj}")
                        return date_obj
                    except ValueError:
                        try:
                            # Формат ISO: "YYYY-MM-DDTHH:MM:SS"
                            date_obj = datetime.strptime(date_value.replace('T', ' ').split('.')[0], "%Y-%m-%d %H:%M:%S")
                            logger.debug(f"Дата из видео ({tag}): {date_obj}")
                            return date_obj
                        except ValueError:
                            logger.debug(f"Не удалось распарсить дату из {tag}: {date_value}")
                            continue
        
        logger.debug(f"Дата создания не найдена в метаданных видео: {file_path}")
        return None
        
    except subprocess.TimeoutExpired:
        logger.warning(f"Таймаут при чтении метаданных видео: {file_path}")
        return None
    except json.JSONDecodeError as e:
        logger.debug(f"Ошибка парсинга JSON от exiftool: {e}")
        return None
    except Exception as e:
        logger.debug(f"Ошибка чтения метаданных видео из {file_path}: {e}")
        return None


def extract_date_from_metadata(file_path: str) -> Optional[datetime]:
    """
    Универсальная функция для извлечения даты из метаданных файла.
    Автоматически определяет тип файла и использует соответствующий метод.
    
    Args:
        file_path: Путь к медиа файлу
        
    Returns:
        Объект datetime или None
    """
    filename = os.path.basename(file_path)
    
    if is_photo(filename):
        return extract_date_from_exif(file_path)
    elif is_video(filename):
        return extract_date_from_video_exiftool(file_path)
    else:
        logger.debug(f"Неизвестный тип файла: {filename}")
        return None


# Проверка доступности библиотек
def check_dependencies():
    """Проверяет доступность необходимых библиотек."""
    exiftool_path = get_exiftool_path()
    status = {
        "Pillow (EXIF)": PIL_AVAILABLE,
        "pillow-heif (HEIC)": HEIF_AVAILABLE,
        "exiftool (Video)": exiftool_path is not None
    }
    if exiftool_path:
        status["exiftool путь"] = exiftool_path
    return status


if __name__ == "__main__":
    # Проверка зависимостей
    print("Проверка зависимостей:")
    deps = check_dependencies()
    for lib, available in deps.items():
        if lib == "exiftool путь":
            print(f"  {lib:30} {available}")
        else:
            status = "✓ Установлен" if available else "✗ Не установлен"
            print(f"  {lib:30} {status}")
    
    print(f"\nПоддерживаемые форматы фото: {', '.join(sorted(PHOTO_EXTENSIONS))}")
    print(f"Поддерживаемые форматы видео: {', '.join(sorted(VIDEO_EXTENSIONS))}")