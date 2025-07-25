"""
Скрипт для збору URL-адрес продуктів з інтернет-магазину Fruugo.

Опис:
- Отримує URL-адреси категорій
- Для кожної категорії переходить по сторінках, збирає всі посилання на продукти.
- Зібрані URL-адреси зберігає у файл ./data/products_urls.json.
- Використовує затримку між запитами для уникнення блокування.
- Відображає прогрес за допомогою tqdm.

Використання:
Запустіть скрипт напряму, попередньо підготувавши файл categories.json з посиланнями на категорії, або викличте collect_products_urls() з іншого модуля.
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
from tqdm import tqdm

# Інтервал очікування для парсингу. Щоб уникнути блокування з боку сайту
PARSE_TIMEOUT = 0.5 # секунди

# Селектори для збору URL-адрес продуктів
PRODUCT_LINK_SELECTOR = '.products-list a'
NEXT_PAGE_SELECTOR = 'a.next-page'
LAST_PAGE_SELECTOR = '.pagination a:nth-last-child(2)'

# Заголовки для HTTP-запитів
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive'
}

# Функція для збереження URL-адрес продуктів у файл
def save_product_urls_to_file(product_urls):
    # Збереження URL-адрес продуктів у файл
    with open("./data/products_urls.json", "w", encoding="utf-8") as f:
        json.dump(product_urls, f, ensure_ascii=False, indent=2)

# Парсимо кожну категорію та отримуємо URL-адреси товарів
def collect_products_urls(categories):
    # Перевірка наявності категорій
    if not categories:
        print("Немає категорій для парсингу. Можливо, файл categories.json не містить категорій.")
        return
    print(f"Обробка {len(categories)} категорій для парсингу.")

    # Проходимося по кожній категорії
    product_urls = []
    for category in tqdm(categories, desc="Категорії", unit="кат."):
        print(f"\nКатегорія: {category}")
        page_url = category + "?pageSize=128" # Збільшуємо розмір сторінки для зменшення кількості запитів

        last_page_number = None
        pbar_pages = None

        while True:
            # Отримуємо HTML-код сторінки категорії
            try:
                response = requests.get(page_url, headers=HEADERS)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
            except requests.RequestException as e:
                print(f"Помилка при отриманні категорії {page_url}: {e}")
                time.sleep(PARSE_TIMEOUT)
                continue

            if not last_page_number:
                # Знаходимо останню сторінку, якщо вона є
                last_page_element = soup.select_one(LAST_PAGE_SELECTOR)
                if last_page_element:
                    last_page_number = int(last_page_element.get_text(strip=True))
                    print(f"Остання сторінка: {last_page_number}")
                    pbar_pages = tqdm(total=last_page_number, desc="Сторінки", unit="стр.")

            if pbar_pages:
                pbar_pages.update(1)

            # Збір URL-адрес продуктів на сторінці категорії
            products = soup.select(PRODUCT_LINK_SELECTOR)
            for product in products:
                url = product.get('href')
                if url:
                    full_url = "https://www.fruugo.co.uk" + url if url.startswith("/") else url
                    product_urls.append(full_url)

            # Перевірка наявності кнопки "Наступна сторінка"
            next_page = soup.select_one(NEXT_PAGE_SELECTOR)
            if not next_page or 'disabled' in next_page.get('class', []):
                print("Наступна сторінка не знайдена або вона вимкнена.")
                break
            else:
                next_page_url = next_page.get('href')
                if next_page_url:
                    page_url = "https://www.fruugo.co.uk" + next_page_url if next_page_url.startswith("/") else next_page_url
                else:
                    print("URL наступної сторінки не знайдено.")
                    break

                # Витягуємо номер сторінки з href, якщо він є
                page_num_match = re.search(r'page=(\d+)', next_page_url or '')
                page_num = int(page_num_match.group(1)) if page_num_match else None

                # Збереження URL-адрес продуктів кожні 10 сторінок
                if page_num is not None and page_num % 10 == 0:
                    save_product_urls_to_file(product_urls)

            # Затримка перед наступним запитом, щоб уникнути блокування
            time.sleep(PARSE_TIMEOUT)

        if pbar_pages:
            pbar_pages.close()

    # Збереження URL-адрес продуктів у файл
    save_product_urls_to_file(product_urls)

    print(f"\nЗібрано {len(product_urls)} URL-адрес продуктів.")
    return product_urls

# Запуск функції збору URL-адрес продуктів
if __name__ == "__main__":
    with open('./data/categories.json', 'r') as file:
        categories = json.load(file)

    collect_products_urls(categories)
