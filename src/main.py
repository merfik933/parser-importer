import json
import os

from parser import collect_products_from_categories
from importer import import_batch

# Ініціалізація логера
from utils.log import init_logger
log = init_logger("main")

def main():
    log.info("Запуск процесу збору та імпорту даних...")
    
    # Перевірка та створення необхідних директорій і файлів
    data_dir = './data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    categories_file = os.path.join(data_dir, 'categories.json')
    if not os.path.exists(categories_file):
        with open(categories_file, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    else:
        with open(categories_file, 'r', encoding='utf-8') as f:
            categories = json.load(f)

        if not categories:
            log.warning("Файл categories.json порожній. Будь ласка, додайте URL-адреси категорій у файл.")
            return
        
    log.info(f"Завантажено {len(categories)} категорій для обробки.")

    # Збір та імпорт даних
    collect_products_from_categories(categories, import_batch)

    log.info("Процес збору та імпорту даних завершено.")

if __name__ == "__main__":
    main()
