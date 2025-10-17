import logging
import os

def init_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Ініціалізує логер, який пише логи у файл та виводить у консоль.

    :param name: Ім'я логера (використовується для імені файлу).
    :param level: Рівень логування (за замовчуванням INFO).
    :return: Ініціалізований логер.
    """

    # Використовуємо передане ім'я як ім'я логера, щоб уникнути колізій
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Додаємо хендлери лише якщо їх ще немає (щоб уникнути дублювання повідомлень)
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Створення директорії для логів, якщо її немає
        logs_dir = './logs'
        os.makedirs(logs_dir, exist_ok=True)

        # Файловий хендлер
        file_handler = logging.FileHandler(os.path.join(logs_dir, f'{name}.log'), mode='w', encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Консольний хендлер
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logger.propagate = False
    return logger