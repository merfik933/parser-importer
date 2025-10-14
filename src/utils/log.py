import logging

def init_logger(level: int = logging.INFO) -> logging.Logger:
    """
    Ініціалізує логер, який пише логи у файл та виводить у консоль.

    :param log_file: Шлях до файлу логів.
    :param level: Рівень логування (за замовчуванням INFO).
    :return: Ініціалізований логер.
    """

    logger = logging.getLogger("app_logger")
    logger.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Файловий хендлер
    file_handler = logging.FileHandler("log.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Консольний хендлер
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger