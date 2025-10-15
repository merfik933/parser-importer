import json
import time
import configparser
import requests
from bs4 import BeautifulSoup
import re

# Ініціалізація логера
from utils.log import init_logger
log = init_logger("parser")

# Завантажуємо конфігурацію
config = configparser.ConfigParser()
config.read('config.ini')

# Отримуємо налаштування з конфігурації
requests_delay = config.getint('PARSER', 'requests_delay', fallback=1)
max_retries = config.getint('PARSER', 'max_retries', fallback=3)
error_delay = config.getint('PARSER', 'error_delay', fallback=60)
batch_size = config.getint('PARSER', 'batch_size', fallback=100)

website_url = "https://www.towerhousewares.co.uk"

# Селектори для парсингу сторінки категорії
PRODUCT_LINK_SELECTOR = '#category-products-default_1651751275465 .push-down-sm .col-xs-12 a'
NEXT_PAGE_SELECTOR = '#category-products-default_1651751275465 #products-holder .col-xs-12 li.btn-pagination a[aria-label="Next"]'
AVAIBLE_COUNT_SELECTOR = "span.available.name"
UNAVAIBLE_COUNT_SELECTOR = "span.name.unavailable"

# Селектори для парсингу сторінки товару
TITLE_SELECTOR = "#product-name-default h1[itemprop='name']"
PRICE_SELECTOR = "#global-text-1655293968607 h2"
REGULAR_PRICE_SELECTOR = "#global-text-1655293968607 p span[style='text-decoration: line-through;']"
SALE_PRICE_SELECTOR = "#global-text-1655293968607 h2"
DESCRIPTION_SELECTOR = "#description_0_1651566202983"
BRAND_SELECTOR = "ul.product-description-spec-list li:has(strong:-soup-contains('Brand')) span"
VARIATION_SELECTOR = ".custom-select option"
VARIATION_SKU_SELECTOR = "#global-code_1651767632362 p"
AVAILABILITY_SELECTOR = "p#stock"
UNAVAIBILITY_SELECTOR = "p#outofstock"
IMAGES_SELECTOR = "#image-carousel_1681814556055 .carousel-inner img.center-block"
CATEGORIES_SELECTOR = "li.crumb.header a"

# Заголовки для HTTP-запитів
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive'
}

# Глобальна змінна для зберігання обробника продуктів
product_handler = None

# Функція для збору даних про продукти з категорій
def collect_products_from_categories(categories, handler):
    # Проходимо по кожній категорії
    for category in categories:
        log.info(f"Збір даних для категорії: {category}")

        # Встановлюємо обробник продуктів
        global product_handler
        product_handler = handler

        # Збираємо дані для категорії
        try:
            collect_category(category)
        except Exception as e:
            print(f"Помилка при зборі даних для категорії {category}: {e}")
            time.sleep(requests_delay)

# Функція для збору даних з категорії
def collect_category(category):
    page_url = category + "?limit=192" # Збільшуємо розмір сторінки для зменшення кількості запитів

    product_count = None

    # Цикл для збору продуктів з категорії по сторінках
    while True:
        response = requests.get(page_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        if not product_count:
            # Знаходимо кількість продуктів
            available_count_element = soup.select_one(AVAIBLE_COUNT_SELECTOR)
            unavaible_count_element = soup.select_one(UNAVAIBLE_COUNT_SELECTOR)
            if available_count_element:
                available_count_text = available_count_element.get_text(strip=True)
                available_count = int(''.join(filter(str.isdigit, available_count_text)))
            else:
                available_count = 0
            if unavaible_count_element:
                unavaible_count_text = unavaible_count_element.get_text(strip=True)
                unavaible_count = int(''.join(filter(str.isdigit, unavaible_count_text)))
            else:
                unavaible_count = 0

            product_count = available_count + unavaible_count
            log.info(f"Знайдено продуктів: {product_count}")

        products = soup.select(PRODUCT_LINK_SELECTOR)
        batch_data = []
        counter = 0

        for product in products:
            url = product.get('href')
            if url:
                full_url = f"{website_url}{url}" if not url.startswith("http") else url
                try:
                    product_data = collect_product_page(full_url)

                    if product_data:
                        batch_data.append(product_data)
                        counter += 1
                        log.info(f"Зібрано продуктів: {counter}/{product_count} з категорії {category}. \n Дані продукту: {product_data}")
                        
                    if len(batch_data) >= batch_size:
                        if product_handler:
                            product_handler(batch_data)
                        batch_data = []
                except Exception as e:
                    log.error(f"Помилка при зборі даних для продукту {full_url}: {e}")
                    time.sleep(error_delay)

                time.sleep(requests_delay) # Затримка між запитами для уникнення блокування

        # Перевірка наявності кнопки "Наступна сторінка"
        next_page = soup.select_one(NEXT_PAGE_SELECTOR)
        if not next_page or 'disabled' in next_page.get('class', []):
            log.info("Наступна сторінка не знайдена або вона вимкнена.")
            break
        else:
            next_page_url = next_page.get('href')
            if next_page_url:
                page_url = f"{website_url}{next_page_url}" if not next_page_url.startswith("http") else next_page_url
                log.info(f"Переходимо до наступної сторінки: {page_url}")
            else:
                log.info("URL наступної сторінки не знайдено.")
                break

        time.sleep(requests_delay)

# Функція для збору даних про продукт за URL
def collect_product_page(url):
    response = requests.get(url, headers=HEADERS)

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
    categories = soup.select(CATEGORIES_SELECTOR)[1:]  # Пропускаємо перший елемент (Home)
    if categories:
        categories = " > ".join([cat.get_text(strip=True) for cat in categories])
    else:
        print(f"Не вдалося знайти категорії продукту на сторінці {url}")
        categories = None

    # Задаємо бренд
    brand = "Tower"

    # Функція для отримання варіації
    def get_variation(variation_url, color_name):
        try:
            # Отримання HTML-сторінки варіації
            response = requests.get(variation_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Отримання SKU
            sku = soup.select_one(VARIATION_SKU_SELECTOR)
            if sku:
                sku = sku.get_text(strip=True).replace("SKU:", "").strip()
            else:
                sku = None

            # Отримання наявності
            availability = soup.select_one(AVAILABILITY_SELECTOR)
            if availability:
                availability = True
            else:
                availability = False

            # Отримання зображень
            images = soup.select(IMAGES_SELECTOR)
            if images:
                images = [img.get('src') for img in images]

        except requests.RequestException as e:
            print(f"Помилка при отриманні варіації з {variation_url}: {e}")
            return None
        return {
            "sku": sku,
            "color": color_name,
            "availability": availability,
            "images": images
        }
    
    # Отримання id та кольорів варіацій
    scripts = soup.find_all("script")
    pattern = re.compile(r"var\s+variant_data\s*=\s*jQuery\.parseJSON\(\s*'(.+?)'\s*\)\s*;", re.DOTALL)
    js_payload = None
    for s in scripts:
        if not s.string:
            text = s.get_text()
        else:
            text = s.string
        m = pattern.search(text)
        if m:
            js_payload = m.group(1)
            break

    # Розбір JSON
    try:
        data = json.loads(js_payload)
    except json.JSONDecodeError as e:
        log.error(f"Помилка JSON при розборі варіацій на сторінці {url}: {e}")
        return None
    
    variations = []
    images = []

    # Шукаємо mapping кольору -> variant id.
    variants = data.get("variants") or {}
    for key, variant_id in variants.items():
        if "~" in key:
            _, name = key.split("~", 1)
        else:
            name = key

        # Замінити в url те що йде після останнього "/" на variant_id
        base_url = url.rsplit('/', 1)[0]
        variation_url = f"{base_url}/{variant_id}"

        variation_data = get_variation(variation_url, name)
        if variation_data:
            variations.append(variation_data)

            # Додаємо унікальні зображення
            for img in variation_data.get("images", []):
                if img not in images:
                    images.append(img)
        
    product_data = {
        "title": title,
        "url": url,
        "regular_price": regular_price,
        "sale_price": sale_price,
        "description": description,
        "categories": categories,
        "images": images,
        "brand": brand,
        "variations": variations,
    }
    return product_data

# Приклад використання функції
if __name__ == "__main__":
    with open('data/categories.json', 'r', encoding='utf-8') as f:
        categories = json.load(f)

    def empty_handler(batch):
        pass

    collect_products_from_categories(categories, empty_handler)


        