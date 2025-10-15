import logging
import os

def init_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Ініціалізує логер, який пише логи у файл та виводить у консоль.

    :param name: Ім'я логера (використовується для імені файлу).
    :param level: Рівень логування (за замовчуванням INFO).
    :return: Ініціалізований логер.
    """

    logger = logging.getLogger("app_logger")
    logger.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Створення директорії для логів, якщо її немає
    logs_dir = './logs'
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # Файловий хендлер
    file_handler = logging.FileHandler(os.path.join(logs_dir, f'{name}.log'), encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Консольний хендлер
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger