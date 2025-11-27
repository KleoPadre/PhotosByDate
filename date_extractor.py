"""
Модуль для умного извлечения дат из имён файлов.
Поддерживает различные форматы дат и игнорирует случайные последовательности цифр.
"""

import re
from datetime import datetime
from typing import Optional
import logging


logger = logging.getLogger("media_organizer")


def extract_date_from_filename(filename: str) -> Optional[datetime]:
    """
    Умное извлечение даты из имени файла.
    Игнорирует случайные последовательности цифр в UUID и хешах.
    
    Args:
        filename: Имя файла для анализа
        
    Returns:
        Объект datetime или None, если дата не найдена
    """
    # Убираем расширение
    name_without_ext = filename.rsplit('.', 1)[0]
    
    # Список паттернов для поиска дат (в порядке приоритета)
    date_patterns = [
        # IMG_20250823_192714, VID_20250823_192714
        (r'(?:IMG|VID|PXL|PHOTO|VIDEO|PANO)[-_](\d{4})(\d{2})(\d{2})[-_]?(\d{2})?(\d{2})?(\d{2})?', 
         'YYYYMMDD_HHMMSS'),
        
        # 2025-08-23, 2025_08_23, 2025.08.23, 2025:08:23
        (r'(\d{4})[-_\.:](\d{2})[-_\.:](\d{2})', 'YYYY-MM-DD'),
        
        # 20250823, только если это отдельная группа
        (r'(?<![0-9A-Fa-f])(\d{4})(\d{2})(\d{2})(?![0-9A-Fa-f])', 'YYYYMMDD'),
        
        # Screenshot 2025-08-23, Photo 2025_08_23
        (r'(?:screenshot|photo|image|snap|pic)[-_\s]+(\d{4})[-_\.:](\d{2})[-_\.:](\d{2})', 'YYYY-MM-DD'),
        
        # 23-08-2025, 23_08_2025, 23.08.2025, 23:08:2025 (день-месяц-год)
        (r'(\d{2})[-_\.:](\d{2})[-_\.:](\d{4})', 'DD-MM-YYYY'),
        
        # 23082025 (день-месяц-год, только если это отдельная группа)
        (r'(?<![0-9A-Fa-f])(\d{2})(\d{2})(\d{4})(?![0-9A-Fa-f])', 'DDMMYYYY'),
    ]
    
    for pattern, format_type in date_patterns:
        match = re.search(pattern, name_without_ext, re.IGNORECASE)
        if match:
            try:
                groups = match.groups()
                
                if format_type == 'YYYYMMDD_HHMMSS':
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    # Проверяем валидность даты
                    if not _is_valid_date(year, month, day):
                        continue
                    # Время опционально
                    hour = int(groups[3]) if groups[3] else 0
                    minute = int(groups[4]) if groups[4] else 0
                    second = int(groups[5]) if groups[5] else 0
                    date_obj = datetime(year, month, day, hour, minute, second)
                    
                elif format_type in ['YYYY-MM-DD', 'YYYYMMDD']:
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    if not _is_valid_date(year, month, day):
                        continue
                    date_obj = datetime(year, month, day)
                    
                elif format_type in ['DD-MM-YYYY', 'DDMMYYYY']:
                    day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                    if not _is_valid_date(year, month, day):
                        continue
                    date_obj = datetime(year, month, day)
                    
                else:
                    continue
                
                logger.debug(f"Дата извлечена из имени '{filename}': {date_obj.strftime('%Y-%m-%d %H:%M:%S')}")
                return date_obj
                
            except (ValueError, IndexError) as e:
                logger.debug(f"Ошибка при разборе даты из '{filename}': {e}")
                continue
    
    logger.debug(f"Не удалось извлечь дату из имени файла: {filename}")
    return None


def _is_valid_date(year: int, month: int, day: int) -> bool:
    """
    Проверяет валидность даты.
    
    Args:
        year: Год (должен быть в диапазоне 1900-2099)
        month: Месяц (1-12)
        day: День (1-31)
        
    Returns:
        True, если дата валидна
    """
    # Проверяем год (разумный диапазон для фото/видео)
    if year < 1900 or year > 2099:
        return False
    
    # Проверяем месяц
    if month < 1 or month > 12:
        return False
    
    # Проверяем день
    if day < 1 or day > 31:
        return False
    
    # Проверяем, что дата действительно существует (например, 31 февраля - нет)
    try:
        datetime(year, month, day)
        return True
    except ValueError:
        return False


def format_date_for_folder(date_obj: datetime) -> tuple:
    """
    Форматирует дату для создания структуры папок.
    
    Args:
        date_obj: Объект datetime
        
    Returns:
        Кортеж (год, "месяц. Название", "день")
    """
    month_names = {
        1: "Январь",
        2: "Февраль",
        3: "Март",
        4: "Апрель",
        5: "Май",
        6: "Июнь",
        7: "Июль",
        8: "Август",
        9: "Сентябрь",
        10: "Октябрь",
        11: "Ноябрь",
        12: "Декабрь"
    }
    
    year = str(date_obj.year)
    month = f"{date_obj.year}.{date_obj.month:02d}"
    day = f"{date_obj.year}.{date_obj.month:02d}.{date_obj.day:02d}"
    
    return year, month, day


# Примеры использования для тестирования
if __name__ == "__main__":
    test_filenames = [
        "IMG_20250823_192714.jpg",
        "VID_20250823_192714.mp4",
        "2025-08-23_photo.jpg",
        "photo_2025_08_23.png",
        "20250823.jpeg",
        "2025:11:13_file.jpg",  # Формат с двоеточиями
        "photo_2025.11.13.png",  # Формат с точками
        "video_2025-11-13.mp4",  # Формат с дефисами
        "1DE4E6D6-D62E-4DB1-A1B6-BBF202001B9159E.jpg",  # Не должна найти дату
        "IMG_2021.jpg",  # Не должна найти дату (недостаточно информации)
        "Screenshot 2025-08-23 at 14.30.45.png",
        "Screenshot 2025:08:23 at 14.30.45.png",  # С двоеточиями
        "23.08.2025_vacation.jpg",
        "23:08:2025_party.jpg",  # День-месяц-год с двоеточиями
        "23082025_party.jpg",
    ]
    
    logging.basicConfig(level=logging.DEBUG)
    
    print("Тестирование извлечения дат из имён файлов:\n")
    for filename in test_filenames:
        date = extract_date_from_filename(filename)
        if date:
            year, month, day = format_date_for_folder(date)
            print(f"✓ {filename:50} -> {year}/{month}/{day}")
        else:
            print(f"✗ {filename:50} -> Дата не найдена")

