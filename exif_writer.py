#!/usr/bin/env python3
"""
Модуль для записи дат в EXIF метаданные фото и видео файлов.
Извлекает даты из имён файлов и записывает их в метаданные.
"""

import os
import subprocess
import logging
from datetime import datetime
from typing import Optional, Tuple
from tqdm import tqdm
from colorama import Fore, Style

from date_extractor import extract_date_from_filename
from metadata_reader import (
    extract_date_from_metadata,
    is_photo,
    is_video,
    is_media_file,
    get_exiftool_path,
    PHOTO_EXTENSIONS,
    VIDEO_EXTENSIONS
)

logger = logging.getLogger("media_organizer")


def write_date_to_photo_exif(file_path: str, date_obj: datetime) -> Tuple[bool, str]:
    """
    Записывает дату создания в EXIF фотографии используя exiftool.
    Это безопасный метод, который сохраняет все существующие EXIF данные и качество изображения.
    
    Args:
        file_path: Путь к файлу фотографии
        date_obj: Объект datetime для записи
        
    Returns:
        Кортеж (успех, сообщение об ошибке)
    """
    exiftool_path = get_exiftool_path()
    if not exiftool_path:
        return False, "exiftool не найден"
    
    if not os.path.exists(file_path):
        return False, f"Файл не найден: {file_path}"
    
    try:
        # Форматируем дату в формат EXIF: "YYYY:MM:DD HH:MM:SS"
        date_str = date_obj.strftime("%Y:%m:%d %H:%M:%S")
        
        # Записываем дату в EXIF теги используя exiftool
        # Это безопасно - exiftool не изменяет само изображение, только метаданные
        result = subprocess.run(
            [
                exiftool_path,
                '-overwrite_original',  # Не создавать backup файлы
                f'-DateTimeOriginal={date_str}',  # Дата съёмки
                f'-CreateDate={date_str}',        # Дата создания
                f'-ModifyDate={date_str}',        # Дата изменения
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = f"exiftool вернул ошибку: {result.stderr}"
            logger.error(f"{error_msg} ({file_path})")
            return False, error_msg
        
        logger.info(f"EXIF дата записана: {file_path} -> {date_str}")
        return True, ""
        
    except subprocess.TimeoutExpired:
        error_msg = "Таймаут при записи EXIF"
        logger.error(f"{error_msg} ({file_path})")
        return False, error_msg
    except Exception as e:
        error_msg = f"Ошибка записи EXIF: {str(e)}"
        logger.error(f"{error_msg} ({file_path})")
        return False, error_msg


def write_date_to_video_metadata(file_path: str, date_obj: datetime) -> Tuple[bool, str]:
    """
    Записывает дату создания в метаданные видео используя exiftool.
    
    Args:
        file_path: Путь к видео файлу
        date_obj: Объект datetime для записи
        
    Returns:
        Кортеж (успех, сообщение об ошибке)
    """
    exiftool_path = get_exiftool_path()
    if not exiftool_path:
        return False, "exiftool не найден"
    
    if not os.path.exists(file_path):
        return False, f"Файл не найден: {file_path}"
    
    try:
        # Форматируем дату в формат exiftool: "YYYY:MM:DD HH:MM:SS"
        date_str = date_obj.strftime("%Y:%m:%d %H:%M:%S")
        
        # Записываем дату в несколько тегов для максимальной совместимости
        result = subprocess.run(
            [
                exiftool_path,
                '-overwrite_original',  # Не создавать backup файлы
                f'-QuickTime:CreateDate={date_str}',
                f'-QuickTime:MediaCreateDate={date_str}',
                f'-QuickTime:TrackCreateDate={date_str}',
                f'-Keys:CreationDate={date_str}',
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = f"exiftool вернул ошибку: {result.stderr}"
            logger.error(f"{error_msg} ({file_path})")
            return False, error_msg
        
        logger.info(f"Метаданные видео записаны: {file_path} -> {date_str}")
        return True, ""
        
    except subprocess.TimeoutExpired:
        error_msg = "Таймаут при записи метаданных видео"
        logger.error(f"{error_msg} ({file_path})")
        return False, error_msg
    except Exception as e:
        error_msg = f"Ошибка записи метаданных видео: {str(e)}"
        logger.error(f"{error_msg} ({file_path})")
        return False, error_msg


def write_date_to_file(file_path: str, date_obj: datetime) -> Tuple[bool, str]:
    """
    Универсальная функция для записи даты в файл.
    Автоматически определяет тип файла и использует соответствующий метод.
    
    Args:
        file_path: Путь к медиа файлу
        date_obj: Объект datetime для записи
        
    Returns:
        Кортеж (успех, сообщение об ошибке)
    """
    filename = os.path.basename(file_path)
    
    if is_photo(filename):
        return write_date_to_photo_exif(file_path, date_obj)
    elif is_video(filename):
        return write_date_to_video_metadata(file_path, date_obj)
    else:
        return False, f"Неподдерживаемый тип файла: {filename}"


def scan_and_update_exif(directory_path: str, logger_obj, recursive: bool = True) -> dict:
    """
    Сканирует директорию и обновляет EXIF даты из имён файлов.
    
    Args:
        directory_path: Путь к директории для сканирования
        logger_obj: Объект логгера
        recursive: Рекурсивный поиск в поддиректориях
        
    Returns:
        Словарь со статистикой: {
            'total': общее количество файлов,
            'updated': обновлено файлов,
            'skipped_has_date': пропущено (уже есть дата в EXIF),
            'skipped_no_date_in_name': пропущено (нет даты в имени),
            'errors': ошибок
        }
    """
    stats = {
        'total': 0,
        'updated': 0,
        'skipped_has_date': 0,
        'skipped_no_date_in_name': 0,
        'errors': 0
    }
    
    # Собираем все медиа файлы
    media_files = []
    all_extensions = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS
    
    if recursive:
        for root, dirs, files in os.walk(directory_path):
            for filename in files:
                if is_media_file(filename):
                    file_path = os.path.join(root, filename)
                    media_files.append(file_path)
    else:
        for filename in os.listdir(directory_path):
            file_path = os.path.join(directory_path, filename)
            if os.path.isfile(file_path) and is_media_file(filename):
                media_files.append(file_path)
    
    if not media_files:
        logger_obj.warning(f"Не найдено медиа файлов в {directory_path}")
        print(f"\n⚠️  Не найдено медиа файлов в указанной папке")
        return stats
    
    stats['total'] = len(media_files)
    
    print(f"\n✓ Найдено файлов: {stats['total']}")
    print(f"Директория: {directory_path}")
    print(f"Рекурсивный поиск: {'Да' if recursive else 'Нет'}\n")
    
    logger_obj.info(f"Начало обновления EXIF для {stats['total']} файлов")
    logger_obj.info(f"Директория: {directory_path}")
    
    # Создаём прогресс-бар
    bar_format = (
        f'{Fore.CYAN}{{desc}}{Style.RESET_ALL}: '
        f'{Fore.GREEN}{{percentage:3.0f}}%{Style.RESET_ALL} '
        f'|{{bar}}| '
        f'{Fore.YELLOW}{{n_fmt}}/{{total_fmt}}{Style.RESET_ALL} '
        f'[{Fore.MAGENTA}{{elapsed}}<{{remaining}}{Style.RESET_ALL}, {{rate_fmt}}]'
    )
    
    print("Обработка файлов:\n")
    
    with tqdm(total=stats['total'],
              unit=' файл',
              desc="Прогресс",
              bar_format=bar_format,
              position=0,
              leave=True,
              colour='green') as pbar:
        
        for idx, file_path in enumerate(media_files, 1):
            filename = os.path.basename(file_path)
            pbar.set_description(f"Обработка: {filename}")
            
            # 1. Проверяем, есть ли уже дата в EXIF
            existing_date = extract_date_from_metadata(file_path)
            if existing_date:
                stats['skipped_has_date'] += 1
                logger_obj.debug(f"[{idx}/{stats['total']}] Пропущен (есть EXIF): {file_path}")
                pbar.update(1)
                continue
            
            # 2. Извлекаем дату из имени файла
            date_from_name = extract_date_from_filename(filename)
            if not date_from_name:
                stats['skipped_no_date_in_name'] += 1
                logger_obj.debug(f"[{idx}/{stats['total']}] Пропущен (нет даты в имени): {file_path}")
                short_path = file_path if len(file_path) <= 60 else "..." + file_path[-57:]
                tqdm.write(
                    f"{Fore.BLUE}{idx}/{stats['total']}{Style.RESET_ALL} "
                    f"{short_path} {Fore.YELLOW}[Нет даты в имени]{Style.RESET_ALL}"
                )
                pbar.update(1)
                continue
            
            # 3. Записываем дату в EXIF
            success, error_msg = write_date_to_file(file_path, date_from_name)
            
            if success:
                stats['updated'] += 1
                logger_obj.info(f"[{idx}/{stats['total']}] Обновлён: {file_path} -> {date_from_name.strftime('%Y-%m-%d %H:%M:%S')}")
                short_path = file_path if len(file_path) <= 60 else "..." + file_path[-57:]
                tqdm.write(
                    f"{Fore.BLUE}{idx}/{stats['total']}{Style.RESET_ALL} "
                    f"{short_path} {Fore.GREEN}→ {date_from_name.strftime('%Y-%m-%d')}{Style.RESET_ALL}"
                )
            else:
                stats['errors'] += 1
                logger_obj.error(f"[{idx}/{stats['total']}] Ошибка: {error_msg} ({file_path})")
                tqdm.write(f"{Fore.RED}⚠️  Ошибка: {filename}: {error_msg}{Style.RESET_ALL}")
            
            pbar.update(1)
    
    # Выводим итоговую статистику
    print(f"\n{'='*60}")
    print("✓ ГОТОВО!")
    print(f"{'='*60}")
    print(f"Всего файлов: {stats['total']}")
    print(f"{Fore.GREEN}Обновлено: {stats['updated']}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Пропущено (уже есть EXIF): {stats['skipped_has_date']}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Пропущено (нет даты в имени): {stats['skipped_no_date_in_name']}{Style.RESET_ALL}")
    print(f"{Fore.RED}Ошибок: {stats['errors']}{Style.RESET_ALL}")
    print(f"{'='*60}\n")
    
    logger_obj.info(f"Обновление EXIF завершено. Обновлено: {stats['updated']}, Пропущено: {stats['skipped_has_date'] + stats['skipped_no_date_in_name']}, Ошибок: {stats['errors']}")
    
    return stats


if __name__ == "__main__":
    # Тестирование
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    print("Модуль для записи дат в EXIF метаданные")
    print("Используйте через media_organizer.py")
