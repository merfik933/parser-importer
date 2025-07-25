import requests
from bs4 import BeautifulSoup
import json
from tqdm import tqdm 

# Збір URL-адрес категорій. Закоментуйте, якщо URL-адреси категорій вже зібрані
# from utils.collect_categories_urls import collect_categories_urls
# collect_categories_urls()

# Отримуємо усі категорії сайту з файлу categories.json.
with open('./data/categories.json', 'r') as file:
    categories = json.load(file)

# from utils.collect_products_urls import collect_products_urls
# collect_products_urls(categories)

with open('./data/products_urls.json', 'r') as file:
    product_urls = json.load(file)

from utils.collect_product_data import get_product_data
products_data = []

# Збір даних про продукти
for url in tqdm(product_urls, desc="Збір продуктів"):
    product_data = get_product_data(url)
    if product_data:
        products_data.append(product_data)

    if len(products_data) % 10 == 0:
        with open('./data/products_data.json', 'w', encoding='utf-8') as f:
            json.dump(products_data, f, ensure_ascii=False, indent=2)

# Фінальне збереження
with open('./data/products_data.json', 'w', encoding='utf-8') as f:
    json.dump(products_data, f, ensure_ascii=False, indent=2)

print(f"✅ Зібрано дані для {len(products_data)} продуктів.")
