"""
Модуль для настройки логирования.
Обеспечивает запись в файл и вывод в консоль.
"""

import logging
import os
from datetime import datetime


def setup_logger(name: str = "media_organizer") -> logging.Logger:
    """
    Настраивает и возвращает логгер с записью в файл и консоль.
    
    Args:
        name: Имя логгера
        
    Returns:
        Настроенный объект логгера
    """
    # Создаём папку для логов, если её нет
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    # Генерируем имя файла лога с текущей датой и временем
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = os.path.join(logs_dir, f"media_organizer_{timestamp}.log")
    
    # Создаём логгер
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Очищаем существующие обработчики (если есть)
    if logger.handlers:
        logger.handlers.clear()
    
    # Формат для логов
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    
    # Обработчик для файла (DEBUG и выше)
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Обработчик для консоли (только WARNING и выше, чтобы не мешать прогресс-бару)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Не выводим это сообщение в консоль, только в файл
    logger.debug(f"Логирование настроено. Лог сохраняется в: {log_filename}")
    
    return logger, log_filename


class LoggerStats:
    """Класс для сбора статистики обработки файлов."""
    
    def __init__(self):
        self.total_files = 0
        self.successful = 0
        self.failed = 0
        self.skipped = 0
        self.no_date = 0
        self.errors = []
        
    def increment_success(self):
        """Увеличить счётчик успешных операций."""
        self.successful += 1
        
    def increment_failed(self, error_msg: str = ""):
        """Увеличить счётчик неудачных операций."""
        self.failed += 1
        if error_msg:
            self.errors.append(error_msg)
            
    def increment_skipped(self):
        """Увеличить счётчик пропущенных файлов."""
        self.skipped += 1
        
    def increment_no_date(self):
        """Увеличить счётчик файлов без даты."""
        self.no_date += 1
        
    def get_summary(self) -> str:
        """
        Получить текстовую сводку статистики.
        
        Returns:
            Строка со статистикой
        """
        summary = f"\n{'='*60}\n"
        summary += "ИТОГОВАЯ СТАТИСТИКА\n"
        summary += f"{'='*60}\n"
        summary += f"Всего обработано файлов: {self.total_files}\n"
        summary += f"Успешно скопировано: {self.successful}\n"
        summary += f"Файлов без даты: {self.no_date}\n"
        summary += f"Пропущено: {self.skipped}\n"
        summary += f"Ошибок: {self.failed}\n"
        
        if self.errors:
            summary += f"\nПервые ошибки:\n"
            for i, error in enumerate(self.errors[:10], 1):
                summary += f"  {i}. {error}\n"
            if len(self.errors) > 10:
                summary += f"  ... и ещё {len(self.errors) - 10} ошибок\n"
        
        summary += f"{'='*60}\n"
        return summary

