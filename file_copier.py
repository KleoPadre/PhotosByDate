import os
import shutil
import logging
from typing import Set, Tuple, Optional, List

# --- Импорты из других модулей ---
# Для корректной работы требуется, чтобы в metadata_reader.py были определены 
# множества PHOTO_EXTENSIONS и VIDEO_EXTENSIONS.
try:
    from metadata_reader import PHOTO_EXTENSIONS, VIDEO_EXTENSIONS
except ImportError:
    # Запасной вариант на случай, если metadata_reader.py не может быть импортирован
    # (например, при тестировании), чтобы избежать сбоя
    PHOTO_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.heic', '.heif', '.cr2', '.nef', 
        '.arw', '.dng', '.raw', '.gif', '.tiff', '.tif', '.bmp', '.webp'
    }
    VIDEO_EXTENSIONS = {
        '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', 
        '.m4v', '.3gp', '.mpeg', '.mpg', '.webm', '.mts'
    }

# --- Константы и Логгер ---
logger = logging.getLogger("media_organizer")
ALL_MEDIA_EXTENSIONS = PHOTO_EXTENSIONS.union(VIDEO_EXTENSIONS)
UNKNOWN_DATE_FOLDER = "Дата неизвестна"


def is_exact_day_folder(folder_name: str) -> bool:
    """Проверяет, соответствует ли имя папки ТОЧНО формату 'YYYY.MM.DD'."""
    # Имя должно быть в формате YYYY.MM.DD (10 символов)
    parts = folder_name.split('.')
    return len(parts) == 3 and all(p.isdigit() for p in parts) and len(folder_name) == 10


def starts_with_day_date(folder_name: str) -> bool:
    """
    Проверяет, начинается ли имя папки с даты 'YYYY.MM.DD'.
    Например: '2025.01.06' или '2023.08.13 тверской полумарафон'.
    """
    if len(folder_name) < 10:
        return False
    
    prefix = folder_name[:10]
    parts = prefix.split('.')
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def is_year_folder(folder_name: str) -> bool:
    """Проверяет, является ли папка годом (4 цифры)."""
    return len(folder_name) == 4 and folder_name.isdigit()


def is_month_folder(folder_name: str) -> bool:
    """Проверяет, является ли папка месяцем (YYYY.MM)."""
    return len(folder_name) == 7 and folder_name.replace('.', '').isdigit() and folder_name[4] == '.'


def validate_paths(source_path: str, destination_path: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет существование и корректность путей источника и назначения.
    
    Returns:
        Кортеж (статус, сообщение_об_ошибке)
    """
    if not os.path.exists(source_path):
        return False, f"Ошибка: Папка источника не найдена: {source_path}"
    if not os.path.isdir(source_path):
        return False, f"Ошибка: Источник не является папкой: {source_path}"
    
    if not os.path.exists(destination_path):
        try:
            os.makedirs(destination_path)
            logger.info(f"Создана папка назначения: {destination_path}")
        except Exception as e:
            return False, f"Ошибка: Не удалось создать папку назначения {destination_path}. {e}"
    elif not os.path.isdir(destination_path):
        return False, f"Ошибка: Назначение не является папкой: {destination_path}"
        
    return True, None


def get_all_media_files(source_path: str, extensions: Set[str] = ALL_MEDIA_EXTENSIONS, skip_organized: bool = False) -> List[str]:
    """
    Рекурсивно получает список всех медиафайлов в исходной папке.
    
    Args:
        source_path: Путь к исходной папке.
        extensions: Множество допустимых расширений файлов.
        skip_organized: Если True, пропускает файлы в уже организованных папках 
                        (Root/YYYY/YYYY.MM/YYYY.MM.DD...).
        
    Returns:
        Список полных путей к медиафайлам.
    """
    media_files = []
    
    # Расширения должны быть в нижнем регистре для корректного сравнения
    lower_extensions = {ext.lower() for ext in extensions}
    
    # Нормализуем путь источника для корректного сравнения
    abs_source_path = os.path.abspath(source_path)

    for root, _, files in os.walk(source_path):
        # Проверяем, нужно ли пропускать эту папку
        if skip_organized:
            current_folder_name = os.path.basename(root)
            
            # Если папка похожа на день (YYYY.MM.DD...)
            # И мы в режиме skip_organized (Source == Destination), то мы пропускаем
            # ЛЮБУЮ папку, которая выглядит как папка дня.
            # Это предотвращает повторную обработку уже организованных папок,
            # а также папок с событиями (2023.08.13 Event), которые пользователь хочет оставить как есть.
            if starts_with_day_date(current_folder_name):
                continue
        
        for file in files:
            # Игнорируем скрытые файлы (начинаются с '.')
            if file.startswith('.'):
                continue
            
            # Получаем расширение и приводим к нижнему регистру
            ext = os.path.splitext(file)[1].lower()
            
            if ext in lower_extensions:
                full_path = os.path.join(root, file)
                media_files.append(full_path)
                
    return media_files


def _get_unique_filename(destination_folder: str, original_filename: str) -> str:
    """
    Внутренняя функция: Генерирует уникальное имя файла в папке назначения, 
    добавляя счетчик (-1, -2, ...) перед расширением, если файл уже существует.
    """
    name, ext = os.path.splitext(original_filename)
    unique_name = original_filename
    counter = 1
    
    while os.path.exists(os.path.join(destination_folder, unique_name)):
        unique_name = f"{name}-{counter}{ext}"
        counter += 1
        
    return unique_name


def copy_file_to_destination(
    file_path: str, 
    destination_path: str, 
    year: str, 
    month: str, 
    day: Optional[str], 
    move: bool,
    grouping: str # 'month', 'day' или 'smart' (который приравнивается к 'day' в этом вызове)
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Копирует или перемещает файл в структуру папок год/месяц/день (или год/месяц).
    Обрабатывает дубликаты.
    
    Args:
        file_path: Полный путь к исходному файлу.
        destination_path: Корневая папка назначения.
        year: Год (строка).
        month: Месяц (строка в формате "01. Январь").
        day: День (строка в формате "01") или None.
        move: True для перемещения, False для копирования.
        grouping: 'day' для год/месяц/день, 'month' для год/месяц.
        
    Returns:
        Кортеж (успех, путь_к_новому_файлу_или_None, сообщение_об_ошибке_или_None)
    """
    filename = os.path.basename(file_path)
    
    # Формируем папку назначения
    # Если grouping = 'day' или 'smart' (что приводит к 'day' в логике media_organizer),
    # используем Год/Месяц/День.
    
    # Проверка на двойную вложенность года или месяца
    dest_basename = os.path.basename(os.path.normpath(destination_path))
    
    if dest_basename == month:
        # Если мы уже в папке месяца (например, 2023.08), создаем только папку дня
        if grouping == 'day' or grouping == 'smart':
            target_folder = os.path.join(destination_path, day)
        else: # grouping == 'month'
            # Мы уже в нужной папке
            target_folder = destination_path
            
    elif dest_basename == year:
        # Если мы уже в папке года, не создаем подпапку года
        if grouping == 'day' or grouping == 'smart':
            target_folder = os.path.join(destination_path, month, day)
        else: # grouping == 'month'
            target_folder = os.path.join(destination_path, month)
    else:
        # Стандартное поведение
        if grouping == 'day' or grouping == 'smart':
            target_folder = os.path.join(destination_path, year, month, day)
        else: # grouping == 'month'
            target_folder = os.path.join(destination_path, year, month)

    # Создаем папку, если она не существует
    try:
        os.makedirs(target_folder, exist_ok=True)
    except Exception as e:
        error_msg = f"Ошибка создания папки {target_folder}: {e}"
        logger.error(f"Файл: {filename}. {error_msg}")
        # Возвращаем False, None, error_msg
        return False, None, error_msg 

    # Обрабатываем дубликаты
    target_filename = _get_unique_filename(target_folder, filename)
    target_file_path = os.path.join(target_folder, target_filename)
    
    operation = shutil.move if move else shutil.copy2
    operation_name = "Перемещение" if move else "Копирование"

    try:
        # Проверяем, не является ли файл сам собой в случае перемещения
        if move and os.path.abspath(file_path) == os.path.abspath(target_file_path):
            log_msg = "Пропущено (идентичный файл, перемещение не требуется)"
            logger.info(f"Файл: {filename}. {log_msg}")
            # Возвращаем False, None, log_msg
            return False, None, log_msg 
            
        operation(file_path, target_file_path)
        
        # Логируем успешную операцию
        if target_filename != filename:
            log_msg = f"{operation_name} в {target_folder} с переименованием в {target_filename}"
        else:
            log_msg = f"{operation_name} в {target_folder}"
            
        logger.info(f"Файл: {filename}. {log_msg}")
        # Возвращаем True, target_file_path, None
        return True, target_file_path, None 
        
    except Exception as e:
        error_msg = f"Ошибка {operation_name.lower()} файла: {e}"
        logger.error(f"Файл: {filename}. {error_msg}")
        # Возвращаем False, None, error_msg
        return False, None, error_msg 


def copy_file_no_date(file_path: str, destination_path: str, move: bool) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Копирует или перемещает файл, у которого не удалось извлечь дату, 
    в папку 'Дата неизвестна'. Обрабатывает дубликаты.
    
    Args:
        file_path: Полный путь к исходному файлу.
        destination_path: Корневая папка назначения.
        move: True для перемещения, False для копирования.
        
    Returns:
        Кортеж (успех, путь_к_новому_файлу_или_None, сообщение_об_ошибке_или_None)
    """
    filename = os.path.basename(file_path)
    target_folder = os.path.join(destination_path, UNKNOWN_DATE_FOLDER)
    
    # Создаем папку, если она не существует
    try:
        os.makedirs(target_folder, exist_ok=True)
    except Exception as e:
        error_msg = f"Ошибка создания папки {target_folder}: {e}"
        logger.error(f"Файл: {filename}. {error_msg}")
        return False, None, error_msg

    # Обрабатываем дубликаты
    target_filename = _get_unique_filename(target_folder, filename)
    target_file_path = os.path.join(target_folder, target_filename)
    
    operation = shutil.move if move else shutil.copy2
    operation_name = "Перемещение" if move else "Копирование"

    try:
        # Проверяем, не является ли файл сам собой в случае перемещения
        if move and os.path.abspath(file_path) == os.path.abspath(target_file_path):
            log_msg = "Пропущено (идентичный файл, перемещение не требуется)"
            logger.info(f"Файл: {filename}. {log_msg}")
            return False, None, log_msg

        operation(file_path, target_file_path)
        
        # Логируем успешную операцию
        if target_filename != filename:
            log_msg = f"{operation_name} в '{UNKNOWN_DATE_FOLDER}' с переименованием в {target_filename}"
        else:
            log_msg = f"{operation_name} в '{UNKNOWN_DATE_FOLDER}'"
            
        logger.info(f"Файл: {filename}. {log_msg}")
        return True, target_file_path, None
        
    except Exception as e:
        error_msg = f"Ошибка {operation_name.lower()} файла: {e}"
        logger.error(f"Файл: {filename}. {error_msg}")
        return False, None, error_msg

# --- НОВЫЕ ФУНКЦИИ ДЛЯ УМНОЙ СОРТИРОВКИ ---



def restructure_for_smart_mode(destination_path: str, logger: logging.Logger) -> int:
    """
    Выполняет второй проход умной сортировки.
    Объединяет папки Год/Месяц/День в Год/Месяц, если в Месяце был только один День.
    
    Args:
        destination_path: Корневая папка назначения.
        logger: Логгер.
        
    Returns:
        Количество объединенных папок.
    """
    restructured_count = 0
    
    # 1. Обход на уровне Года
    for year_folder_name in os.listdir(destination_path):
        year_path = os.path.join(destination_path, year_folder_name)
        # Проверяем, что это папка и похоже на год (4 цифры)
        if not os.path.isdir(year_path) or not year_folder_name.isdigit() or len(year_folder_name) != 4:
            continue

        # 2. Обход на уровне Месяца
        for month_folder_name in os.listdir(year_path):
            month_path = os.path.join(year_path, month_folder_name)
            # Проверяем, что это папка
            if not os.path.isdir(month_path):
                continue
                
            # Проверяем, что папка месяца соответствует формату "YYYY.MM"
            if not (len(month_folder_name) == 7 and month_folder_name.replace('.', '').isdigit() and month_folder_name[4] == '.'):
                continue

            # 3. Проверка содержимого папки Месяца
            all_items = os.listdir(month_path)
            
            # Выделяем только папки, которые могут быть папками Дня ("DD")
            day_folders = [d for d in all_items 
                          if os.path.isdir(os.path.join(month_path, d)) and is_exact_day_folder(d)]
            
            # Определяем, есть ли другие элементы (файлы, не-DD папки) в папке Месяца
            other_items = [item for item in all_items 
                           if not (os.path.isdir(os.path.join(month_path, item)) and is_exact_day_folder(item))]
            
            # Критерий умной сортировки: Внутри папки Месяца есть ТОЛЬКО ОДНА папка "Дня"
            # и НЕТ ДРУГИХ ФАЙЛОВ/ПАПОК, которые могли бы помешать удалению Day_folder.
            if len(day_folders) == 1 and not other_items:
                day_folder_name = day_folders[0]
                day_path = os.path.join(month_path, day_folder_name)
                
                logger.info(f"Обнаружен кандидат на объединение: {day_path} -> {month_path}")

                try:
                    # 4. Перемещение содержимого "Дня" в "Месяц"
                    for item_name in os.listdir(day_path):
                        src_item = os.path.join(day_path, item_name)
                        dst_item = os.path.join(month_path, item_name)
                        
                        # Обработка дубликатов (хотя маловероятно, но для безопасности)
                        if os.path.exists(dst_item):
                            # Если есть конфликт, переименовываем
                            unique_name = _get_unique_filename(month_path, item_name)
                            dst_item = os.path.join(month_path, unique_name)
                            logger.warning(f"Конфликт имён при объединении. '{item_name}' переименован в '{unique_name}'")
                        
                        shutil.move(src_item, dst_item)
                        
                    # 5. Удаление пустой папки "Дня"
                    os.rmdir(day_path)
                    
                    logger.info(f"Успешно объединено: папка '{day_folder_name}' удалена, файлы перемещены в '{month_path}'")
                    restructured_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка при объединении папки {day_path} в {month_path}: {e}")
                    
    return restructured_count