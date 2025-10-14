import json
import os

from src.utils.log import init_logger
log = init_logger()

def main():
    log.info("Запуск процесу збору та імпорту даних...")
    
    data_dir = './data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    categories_file = os.path.join(data_dir, 'categories.json')
    if not os.path.exists(categories_file):
        from src.utils.categories_collector import collect_categories_urls
        categories = collect_categories_urls()

        with open(categories_file, 'w', encoding='utf-8') as f:
            json.dump(categories, f, ensure_ascii=False, indent=2)
    else:
        with open(categories_file, 'r', encoding='utf-8') as f:
            categories = json.load(f)


    from src.parser import collect_products_from_categories
    from src.importer import import_batch

    collect_products_from_categories(categories, import_batch)

    log.info("Процес збору та імпорту даних завершено.")

if __name__ == "__main__":
    main()
