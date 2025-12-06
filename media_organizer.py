#!/usr/bin/env python3
"""
Медиа Сортировщик - умная сортировка фото и видео по папкам год/месяц/день.

Скрипт извлекает даты из имён файлов, EXIF и метаданных видео,
затем копирует файлы в структуру папок год/месяц/день с обработкой дубликатов.
"""

import os
import sys
import time
from datetime import datetime
from typing import Optional

from tqdm import tqdm
from colorama import Fore, Style, init

# Инициализируем colorama для поддержки цветов в Windows
init(autoreset=True)

from logger_config import setup_logger, LoggerStats
from date_extractor import extract_date_from_filename, format_date_for_folder
from metadata_reader import (
    extract_date_from_metadata, 
    is_media_file, 
    PHOTO_EXTENSIONS, 
    VIDEO_EXTENSIONS
)
from file_copier import (
    copy_file_to_destination,
    copy_file_no_date,
    get_all_media_files,
    validate_paths,
    restructure_for_smart_mode # НОВАЯ ФУНКЦИЯ ДЛЯ УМНОЙ СОРТИРОВКИ
)
from video_compressor import scan_and_compress
from exif_writer import scan_and_update_exif


def get_grouping_mode_input() -> str:
    """
    Запрашивает у пользователя режим группировки файлов.
    
    Returns:
        Строка: 'day', 'month' или 'smart'
    """
    while True:
        print("Выберите режим группировки файлов:")
        print(f"  1 - {Fore.CYAN}По датам (Год/Месяц/День){Style.RESET_ALL}")
        print(f"  2 - {Fore.CYAN}По месяцам (Год/Месяц){Style.RESET_ALL}")
        print(f"  3 - {Fore.CYAN}Умная сортировка (Год/Месяц/День, если разные даты; Год/Месяц, если одна дата){Style.RESET_ALL}")
        
        mode_choice = input("\nВаш выбор (1, 2 или 3): ").strip()
        
        if mode_choice == "1":
            grouping_mode = "day"
            print(f"✓ Выбран режим: {Fore.CYAN}Год/Месяц/День{Style.RESET_ALL}\n")
            return grouping_mode
        elif mode_choice == "2":
            grouping_mode = "month"
            print(f"✓ Выбран режим: {Fore.CYAN}Год/Месяц{Style.RESET_ALL}\n")
            return grouping_mode
        elif mode_choice == "3":
            grouping_mode = "smart"
            print(f"✓ Выбран режим: {Fore.CYAN}Умная сортировка{Style.RESET_ALL}\n")
            return grouping_mode
        else:
            print(f"{Fore.RED}⚠️  Неверный выбор. Введите 1, 2 или 3.{Style.RESET_ALL}\n")


def get_user_input() -> tuple:
    """
    Запрашивает у пользователя пути к папкам источника и назначения,
    а также режим работы и группировки.
    
    Returns:
        Кортеж (путь_источника, путь_назначения, режим_операции, обработка_без_даты, режим_группировки)
        режим_операции: 'copy' или 'move'
        обработка_без_даты: True (копировать в "Дата неизвестна") или False (пропустить)
        режим_группировки: 'day', 'month' или 'smart'
    """
    print("=" * 60)
    print("МЕДИА СОРТИРОВЩИК")
    print("=" * 60)
    print("\nСортировка фото и видео по папкам год/месяц/день")
    print("Поддержка EXIF, метаданных видео и умного распознавания дат в именах\n")
    
    # Запрашиваем путь к источнику
    while True:
        source_path = input("Введите путь к папке-источнику: ").strip()
        
        if not source_path:
            print("⚠️  Путь не может быть пустым. Попробуйте снова.\n")
            continue
        
        # Убираем кавычки (одинарные и двойные), которые могут быть при копировании пути
        source_path = source_path.strip("'\"")
        
        # Разворачиваем ~ в домашнюю папку
        source_path = os.path.expanduser(source_path)
        
        if not os.path.exists(source_path):
            print(f"⚠️  Папка не существует: {source_path}\n")
            continue
        
        if not os.path.isdir(source_path):
            print(f"⚠️  Это не папка: {source_path}\n")
            continue
        
        break
    
    # Запрашиваем путь к назначению
    while True:
        destination_path = input("Введите путь к папке-назначению: ").strip()
        
        if not destination_path:
            print("⚠️  Путь не может быть пустым. Попробуйте снова.\n")
            continue
        
        # Убираем кавычки (одинарные и двойные), которые могут быть при копировании пути
        destination_path = destination_path.strip("'\"")
        
        # Разворачиваем ~ в домашнюю папку
        destination_path = os.path.expanduser(destination_path)
        
        # Проверяем валидность путей
        valid, error_msg = validate_paths(source_path, destination_path)
        if not valid:
            print(f"⚠️  {error_msg}\n")
            continue
        
        break
    
    print()
    
    # Выбор режима операции
    while True:
        print("Выберите режим работы:")
        print(f"  1 - {Fore.GREEN}Копирование (исходные файлы остаются на месте){Style.RESET_ALL}")
        print(f"  2 - {Fore.RED}Перемещение (исходные файлы будут удалены){Style.RESET_ALL}")
        
        mode_choice = input("\nВаш выбор (1 или 2): ").strip()
        
        if mode_choice == "1":
            operation_mode = "copy"
            print(f"✓ Выбран режим: {Fore.GREEN}Копирование{Style.RESET_ALL}\n")
            break
        elif mode_choice == "2":
            operation_mode = "move"
            print(f"✓ Выбран режим: {Fore.RED}Перемещение{Style.RESET_ALL}\n")
            break
        else:
            print(f"{Fore.RED}⚠️  Неверный выбор. Введите 1 или 2.{Style.RESET_ALL}\n")
            
    # Выбор режима группировки
    grouping_mode = get_grouping_mode_input()
    
    # Выбор обработки файлов без даты
    while True:
        print("Что делать с файлами, у которых не найдена дата?")
        print(f"  1 - {Fore.GREEN}Сохранить в папку 'Дата неизвестна'{Style.RESET_ALL}")
        print(f"  2 - {Fore.RED}Пропустить такие файлы{Style.RESET_ALL}")
        
        no_date_choice = input("\nВаш выбор (1 или 2): ").strip()
        
        if no_date_choice == "1":
            process_no_date = True
            print(f"✓ Файлы без даты будут {Fore.GREEN}сохранены{Style.RESET_ALL}\n")
            break
        elif no_date_choice == "2":
            process_no_date = False
            print(f"✓ Файлы без даты будут {Fore.RED}пропущены{Style.RESET_ALL}\n")
            break
        else:
            print(f"{Fore.RED}⚠️  Неверный выбор. Введите 1 или 2.{Style.RESET_ALL}\n")
    
    return source_path, destination_path, operation_mode, process_no_date, grouping_mode


def determine_file_date(file_path: str, filename: str) -> Optional[datetime]:
    """
    Определяет дату файла по приоритету:
    1. Из имени файла
    2. Из EXIF/метаданных
    
    Args:
        file_path: Полный путь к файлу
        filename: Имя файла
        
    Returns:
        Объект datetime или None
    """
    # Приоритет 1: Дата из имени файла
    date = extract_date_from_filename(filename)
    if date:
        return date
    
    # Приоритет 2: Дата из метаданных (EXIF для фото, metadata для видео)
    date = extract_date_from_metadata(file_path)
    if date:
        return date
    
    return None


def process_files(source_path: str, destination_path: str, 
                 logger, stats: LoggerStats, operation_mode: str, 
                 process_no_date: bool, grouping_mode: str) -> str:
    """
    Основная функция обработки файлов.
    
    Args:
        source_path: Путь к папке-источнику
        destination_path: Путь к папке-назначению
        logger: Логгер
        stats: Объект статистики
        operation_mode: 'copy' или 'move'
        process_no_date: True/False
        grouping_mode: 'day', 'month' или 'smart'
        
    Returns:
        Путь к файлу лога
    """
    # Получаем список всех медиа файлов
    all_extensions = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS
    
    # Проверяем, совпадают ли пути источника и назначения
    # Если совпадают, включаем "умный пропуск" уже организованных папок
    skip_organized = os.path.abspath(source_path) == os.path.abspath(destination_path)
    
    media_files = get_all_media_files(source_path, all_extensions, skip_organized=skip_organized)
    
    if not media_files:
        logger.warning("Не найдено медиа файлов для обработки")
        print("\n⚠️  Не найдено медиа файлов в указанной папке")
        return
    
    stats.total_files = len(media_files)
    
    is_move = operation_mode == 'move'
    mode_text = "Перемещение" if is_move else "Копирование"
    mode_color = Fore.RED if is_move else Fore.GREEN
    
    # Определяем режим группировки для первого прохода (копирование/перемещение)
    initial_grouping = grouping_mode
    grouping_text = ""
    
    if grouping_mode == 'smart':
        # Для умной сортировки сначала все кладем в папки по дням
        initial_grouping = 'day'
        grouping_text = "Умная сортировка (Начальная: Год/Месяц/День)"
    elif grouping_mode == 'day':
        grouping_text = "Год/Месяц/День"
    else: # 'month'
        grouping_text = "Год/Месяц"
    
    print(f"\n✓ Найдено файлов: {stats.total_files}")
    print(f"Источник: {source_path}")
    print(f"Назначение: {destination_path}")
    print(f"Режим: {mode_color}{mode_text}{Style.RESET_ALL}")
    print(f"Группировка: {Fore.CYAN}{grouping_text}{Style.RESET_ALL}")
    print(f"Файлы без даты: {'Сохранять' if process_no_date else 'Пропускать'}\n")
    
    logger.info(f"Начало обработки {stats.total_files} файлов")
    logger.info(f"Источник: {source_path}")
    logger.info(f"Назначение: {destination_path}")
    logger.info(f"Режим: {mode_text}")
    logger.info(f"Группировка: {grouping_text}")
    logger.info(f"Файлы без даты: {'Сохранять' if process_no_date else 'Пропускать'}")
    
    # Засекаем время начала
    start_time = time.time()
    
    # Обрабатываем файлы с прогресс-баром (ПЕРВЫЙ ПРОХОД)
    operation_text = "Перемещение" if is_move else "Копирование"
    print(f"{operation_text} файлов:\n")
    
    # Создаём цветной прогресс-бар
    bar_format = (
        f'{Fore.CYAN}{{desc}}{Style.RESET_ALL}: '
        f'{Fore.GREEN}{{percentage:3.0f}}%{Style.RESET_ALL} '
        f'|{{bar}}| '
        f'{Fore.YELLOW}{{n_fmt}}/{{total_fmt}}{Style.RESET_ALL} '
        f'[{Fore.MAGENTA}{{elapsed}}<{{remaining}}{Style.RESET_ALL}, {{rate_fmt}}]'
    )
    
    with tqdm(total=stats.total_files, 
              unit=' файл',
              desc="Прогресс",
              bar_format=bar_format,
              position=0,
              leave=True,
              colour='green') as pbar:
        
        for idx, file_path in enumerate(media_files, 1):
            filename = os.path.basename(file_path)
            
            # Обновляем описание прогресс-бара текущим файлом
            pbar.set_description(f"Обработка: {filename}")

            # Определяем дату файла
            file_date = determine_file_date(file_path, filename)
            
            if file_date:
                # Форматируем дату для структуры папок
                year, month, day = format_date_for_folder(file_date)
                
                # Копируем или перемещаем файл, используя initial_grouping
                success, dest_path, error_msg = copy_file_to_destination(
                    file_path, destination_path, year, month, day, 
                    move=is_move, grouping=initial_grouping # Используем initial_grouping
                )
                
                if success:
                    stats.increment_success()
                    logger.info(f"[{idx}/{stats.total_files}] {file_path} -> {dest_path}")
                    
                else:
                    stats.increment_failed(error_msg)
                    logger.error(f"[{idx}/{stats.total_files}] Ошибка: {error_msg}")
            else:
                # Файл без даты
                if process_no_date:
                    # Копируем/перемещаем в специальную папку
                    success, dest_path, error_msg = copy_file_no_date(file_path, destination_path, move=is_move)
                    
                    if success:
                        stats.increment_no_date()
                        logger.info(f"[{idx}/{stats.total_files}] Файл без даты: {file_path} -> {dest_path}")
                        
                        # Выводим информацию о файле без даты с цветом
                        short_source = file_path if len(file_path) <= 60 else "..." + file_path[-57:]
                        tqdm.write(
                            f"{Fore.BLUE}{idx}/{stats.total_files}{Style.RESET_ALL} "
                            f"{short_source} {Fore.YELLOW}→{Style.RESET_ALL} "
                            f"{Fore.YELLOW}[Дата неизвестна]{Style.RESET_ALL}"
                        )
                    else:
                        stats.increment_failed(error_msg)
                        logger.error(f"[{idx}/{stats.total_files}] Ошибка: {error_msg}")
                        tqdm.write(f"{Fore.RED}⚠️  Ошибка при обработке {filename}: {error_msg}{Style.RESET_ALL}")
                else:
                    # Пропускаем файл без даты
                    stats.increment_skipped()
                    logger.info(f"[{idx}/{stats.total_files}] Пропущен файл без даты: {file_path}")
                    short_source = file_path if len(file_path) <= 60 else "..." + file_path[-57:]
                    tqdm.write(
                        f"{Fore.BLUE}{idx}/{stats.total_files}{Style.RESET_ALL} "
                        f"{short_source} {Fore.MAGENTA}[Пропущен]{Style.RESET_ALL}"
                    )
            
            # Обновляем прогресс-бар
            pbar.update(1)
            
    # --- ВТОРОЙ ПРОХОД: УМНАЯ СОРТИРОВКА ---
    if grouping_mode == 'smart' and (stats.successful > 0 or stats.no_date > 0):
        logger.info("-" * 60)
        logger.info("Начало Второго Прохода: Умная Сортировка")
        print(f"\n{Fore.CYAN}Второй проход: Умная Сортировка...{Style.RESET_ALL}")
        
        # Вызываем функцию реструктуризации
        smart_restructures = restructure_for_smart_mode(destination_path, logger)
        
        logger.info(f"Завершено. Объединено {smart_restructures} папок.")
        print(f"✓ {Fore.GREEN}Умная сортировка завершена.{Style.RESET_ALL} Объединено папок: {smart_restructures}")
        logger.info("-" * 60)
    
    # Вычисляем время выполнения
    elapsed_time = time.time() - start_time
    hours = int(elapsed_time // 3600)
    minutes = int((elapsed_time % 3600) // 60)
    seconds = int(elapsed_time % 60)
    
    time_str = ""
    if hours > 0:
        time_str = f"{hours}ч {minutes}м {seconds}с"
    elif minutes > 0:
        time_str = f"{minutes}м {seconds}с"
    else:
        time_str = f"{seconds}с"
    
    # Выводим итоговую статистику
    print(f"\n{'='*60}")
    print("✓ ГОТОВО!")
    print(f"{'='*60}")
    print(f"Обработано файлов: {stats.total_files}")
    print(f"Успешно скопировано: {stats.successful}")
    print(f"Файлов без даты: {stats.no_date}")
    print(f"Пропущено: {stats.skipped}")
    print(f"Ошибок: {stats.failed}")
    print(f"Время выполнения: {time_str}")
    
    # Логируем статистику
    logger.info(stats.get_summary())
    logger.info(f"Время выполнения: {time_str}")


def main():
    """Главная функция программы."""
    try:
        # Настраиваем логгер
        logger, log_filename = setup_logger()
        stats = LoggerStats()
        
        print("=" * 60)
        print("МЕДИА ИНСТРУМЕНТЫ")
        print("=" * 60)
        print("Выберите действие:")
        print(f"  1 - {Fore.CYAN}Сортировка фото и видео{Style.RESET_ALL}")
        print(f"  2 - {Fore.CYAN}Сжатие видео{Style.RESET_ALL}")
        print(f"  3 - {Fore.CYAN}Обновить EXIF даты из названий файлов{Style.RESET_ALL}")
        
        action_choice = input("\nВаш выбор (1, 2 или 3): ").strip()
        
        if action_choice == "2":
            # Режим сжатия видео
            print(f"\n✓ Выбран режим: {Fore.CYAN}Сжатие видео{Style.RESET_ALL}\n")
            
            while True:
                target_path = input("Введите путь к папке с видео: ").strip()
                target_path = target_path.strip("'\"")
                target_path = os.path.expanduser(target_path)
                
                if not os.path.exists(target_path) or not os.path.isdir(target_path):
                    print(f"⚠️  Папка не существует: {target_path}\n")
                    continue
                break
            
            scan_and_compress(target_path)
            
        elif action_choice == "3":
            # Режим обновления EXIF дат
            print(f"\n✓ Выбран режим: {Fore.CYAN}Обновить EXIF даты из названий файлов{Style.RESET_ALL}\n")
            
            print(f"{Fore.YELLOW}⚠️  ВНИМАНИЕ: Эта операция изменит оригинальные файлы!{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}   Рекомендуется сделать резервную копию перед началом.{Style.RESET_ALL}\n")
            
            while True:
                target_path = input("Введите путь к папке с медиа файлами: ").strip()
                target_path = target_path.strip("'\"")
                target_path = os.path.expanduser(target_path)
                
                if not os.path.exists(target_path) or not os.path.isdir(target_path):
                    print(f"⚠️  Папка не существует: {target_path}\n")
                    continue
                break
            
            # Спрашиваем про рекурсивный поиск
            while True:
                recursive_choice = input("\nИскать файлы в подпапках? (1 - Да, 2 - Нет): ").strip()
                if recursive_choice == "1":
                    recursive = True
                    print(f"✓ Рекурсивный поиск: {Fore.GREEN}Включён{Style.RESET_ALL}\n")
                    break
                elif recursive_choice == "2":
                    recursive = False
                    print(f"✓ Рекурсивный поиск: {Fore.RED}Выключен{Style.RESET_ALL}\n")
                    break
                else:
                    print(f"{Fore.RED}⚠️  Неверный выбор. Введите 1 или 2.{Style.RESET_ALL}\n")
            
            # Финальное подтверждение
            confirm = input(f"\n{Fore.YELLOW}Продолжить? Файлы будут изменены! (yes/no): {Style.RESET_ALL}").strip().lower()
            if confirm in ['yes', 'y', 'да', 'д']:
                scan_and_update_exif(target_path, logger, recursive=recursive)
                print(f"Лог сохранён в: {log_filename}")
                print(f"{'='*60}\n")
            else:
                print(f"\n{Fore.RED}Операция отменена пользователем{Style.RESET_ALL}\n")
            
        else:
            # Режим сортировки (по умолчанию)
            if action_choice != "1":
                print(f"По умолчанию выбран режим: {Fore.CYAN}Сортировка фото и видео{Style.RESET_ALL}\n")
            
            # Получаем пути и настройки от пользователя
            source_path, destination_path, operation_mode, process_no_date, grouping_mode = get_user_input()
            
            # Обрабатываем файлы
            process_files(source_path, destination_path, logger, stats, operation_mode, process_no_date, grouping_mode)
            
            # Сообщаем где лог
            print(f"Лог сохранён в: {log_filename}")
            print(f"{'='*60}\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Операция прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()