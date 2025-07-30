from tqdm import tqdm
import json
import time
import configparser
import requests
from bs4 import BeautifulSoup
import re

# Завантажуємо конфігурацію
config = configparser.ConfigParser()
config.read('config.ini')

# Отримуємо налаштування з конфігурації
use_proxy = config.getboolean('DEFAULT', 'use_proxy', fallback=False)
max_threads = config.getint('DEFAULT', 'max_threads', fallback=5)
max_retries = config.getint('DEFAULT', 'max_retries', fallback=3)
requests_delay = config.getint('DEFAULT', 'requests_delay', fallback=1)

# Якщо використовується проксі, завантажуємо список проксі з файлу
if use_proxy:
    with open('proxies.txt', 'r', encoding='utf-8') as f:
        proxies = [line.strip() for line in f if line.strip()]

# Селектори для парсингу
PRODUCT_LINK_SELECTOR = '.products-list a'
NEXT_PAGE_SELECTOR = 'a.next-page'
LAST_PAGE_SELECTOR = '.pagination a:nth-last-child(2)'

TITLE_SELECTOR = ".Product__Details h1.js-product-title"
PRICE_SELECTOR = ".js-meta-price"
REGULAR_PRICE_SELECTOR = ".Product__Details .Product__Price del"
SALE_PRICE_SELECTOR = ".js-meta-price"
DESCRIPTION_SELECTOR = "#description"
BRAND_SELECTOR = "ul.product-description-spec-list li:has(strong:-soup-contains('Brand')) span"
VARIATION_SELECTOR = ".custom-select option"
SIZE_SELECTOR = ".Product__Details .Product__Title label[for='Colour'] span"
COLOR_SELECTOR = ".Product__Details .Product__Title label[for='Size'] span"
AVAILABILITY_SELECTOR = ".Product__BuyBox strong"
IMAGES_SELECTOR = "button.js-gallery-thumb"
IMAGE_SELECTOR = "#main .Product .Product__Top .Product__Gallery .ProductGallery.js-hover-zoom img"
CATEGORIES_SELECTOR = ".Product__Top li.breadcrumb-item a"

# Заголовки для HTTP-запитів
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive'
}

# Функція для збору даних про продукти з категорій
def collect_product_data(categories, product_handler):
    # Прогресбар для відстеження прогресу
    with tqdm(categories, desc="Категорія: ", unit="кат.") as cat_bar:
        # Проходимо по кожній категорії
        for category in cat_bar:
            # Оновлюємо прогресбар з назвою категорії
            cat_bar.set_description(f"Категорія: {category}")

            # Збираємо дані для категорії
            try:
                collect_category(category, product_handler)
            except Exception as e:
                print(f"Помилка при зборі даних для категорії {category}: {e}")

# Функція для збору даних з категорії
def collect_category(category, product_handler):
    page_url = category + "?pageSize=128" # Збільшуємо розмір сторінки для зменшення кількості запитів

    last_page_number = None
    page_bar = None

    # Цикл для збору продуктів з категорії по сторінках
    while True:
        response = requests.get(page_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        if not last_page_number:
            # Знаходимо останню сторінку, якщо вона є
            last_page_element = soup.select_one(LAST_PAGE_SELECTOR)
            if last_page_element:
                last_page_number = int(last_page_element.get_text(strip=True))
                page_bar = tqdm(total=last_page_number, desc="Парсинг сторінок категорії", unit="стр.")

        if page_bar:
            page_bar.update(1)
        
        products = soup.select(PRODUCT_LINK_SELECTOR)
        with tqdm(products, desc="Збір продуктів", unit="продукт") as product_bar:
            for product in product_bar:
                url = product.get('href')
                if url:
                    full_url = "https://www.fruugo.co.uk" + url if url.startswith("/") else url
                    try:
                        product_data = collect_product_page(full_url)
                        if product_data:
                            product_handler(product_data)
                    except Exception as e:
                        print(f"Помилка при зборі даних для продукту {full_url}: {e}")

                    time.sleep(requests_delay)  # Затримка між запитами для уникнення блокування

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

        time.sleep(requests_delay)

# Функція для збору даних про продукт за URL
def collect_product_page(url):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    # Отримання заголовку
    title = soup.select_one(TITLE_SELECTOR)
    if title:
        title = title.get_text(strip=True)
    else:
        print(f"Не вдалося знайти назву продукту на сторінці {url}")
        return None

    # Функція для очищення та перетворення тексту ціни у число
    def extract_price(text):
        if not text:
            return None
        cleaned = re.sub(r"[^\d.]", "", text)
        try:
            return float(cleaned)
        except ValueError:
            return None

    # Отримання цін
    regular_price = soup.select_one(REGULAR_PRICE_SELECTOR)
    if regular_price:
        regular_price = extract_price(regular_price.get_text(strip=True))

        sale_price = soup.select_one(SALE_PRICE_SELECTOR)
        if sale_price:
            sale_price = extract_price(sale_price.get_text(strip=True))
        else:
            sale_price = None
    else:
        sale_price = None

        regular_price = soup.select_one(PRICE_SELECTOR)
        if regular_price:
            regular_price = extract_price(regular_price.get_text(strip=True))
        else:
            print(f"Не вдалося знайти ціну продукту на сторінці {url}")
            return None

    # Отримання опису
    description = soup.select_one(DESCRIPTION_SELECTOR)
    if description:
        description = str(description)
    else:
        print(f"Не вдалося знайти опис продукту на сторінці {url}")
        return None

    # Отримання категорії
    categories = soup.select_one(CATEGORIES_SELECTOR)
    if categories:
        categories = " > ".join([cat.get_text(strip=True) for cat in categories])
    else:
        print(f"Не вдалося знайти категорію продукту на сторінці {url}")
        return None

    # Отримання бренду
    brand = soup.select_one(BRAND_SELECTOR)
    if brand:
        brand = brand.get_text(strip=True)
    else:
        brand = None

    # Функція для отримання варіації за URL
    def get_variation_by_url(variation_url):
        try:
            match = re.search(r'/p-(\d+)-(\d+)', variation_url)
            if match:
                product_id, variant_id = match.groups()
                sku = f"SKU-{product_id}-{variant_id}"
            else:
                print(f"Не вдалося отримати ID продукту з URL: {variation_url}")
                return None
            
            response = requests.get(variation_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Отримання розміру
            size = soup.select(SIZE_SELECTOR)
            if size:
                size = size[0].get_text(strip=True)
            else:
                size = None

            # Отримання кольору
            color = soup.select(COLOR_SELECTOR)
            if color:
                color = color[0].get_text(strip=True)
            else:
                color = None

            # Отримання наявності
            availability = soup.select_one(AVAILABILITY_SELECTOR)
            if availability:
                availability_text = availability.get_text(strip=True)
                availability = availability_text == "In stock"
            else:
                availability = None

            # Отримання зображень
            images = soup.select(IMAGES_SELECTOR)
            if images:
                images = [img.get('data-image') for img in images]
            else:
                image = soup.select_one(IMAGE_SELECTOR)
                if image:
                    images = [image.get('src')]
                else:
                    images = []

        except requests.RequestException as e:
            print(f"Помилка при отриманні варіації з {variation_url}: {e}")
            return None
        return {
            "sku": sku,
            "size": size,
            "color": color,
            "availability": availability,
            "images": images
        }
    
    # Отримання id варіацій
    variations_options = soup.select(VARIATION_SELECTOR)
    variations = []
    all_variation_ids = []
    for variation_option in variations_options:
        value = variation_option.get('value', '')

        match = re.search(r'\[([^\]]+)\]', value)
        if match:
            ids = match.group(1).split(', ')
        
        for id in ids:
            if id in all_variation_ids:
                continue

            all_variation_ids.append(id)
            variation_url = re.sub(r'(p-\d+)', rf'\1-{id}', url)

            variation_data = get_variation_by_url(variation_url)
            if variation_data:
                variations.append(variation_data)
    
    product_data = {
        "title": title,
        "url": url,
        "regular_price": regular_price,
        "sale_price": sale_price,
        "description": description,
        "categories": categories,
        "brand": brand,
        "variations": variations,
    }
    return product_data

# Приклад використання функції
if __name__ == "__main__":
    with open('data/categories.json', 'r', encoding='utf-8') as f:
        categories = json.load(f)

    products = []

    def test_handler(data):
        products.append(data)

        with open('data/products_data.json', 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=2)

    collect_product_data(categories, test_handler)


        