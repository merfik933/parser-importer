import json
import time
import configparser
import requests
from bs4 import BeautifulSoup
import pandas as pd

# Ініціалізація логера
from utils.log import init_logger
log = init_logger("reviews")

import os
from dotenv import load_dotenv
load_dotenv()
WC_URL = os.getenv("WC_URL")
WC_KEY = os.getenv("WC_KEY")
WC_SECRET = os.getenv("WC_SECRET")
WC_USERNAME = os.getenv("WC_USERNAME")
WC_PASSWORD = os.getenv("WC_PASSWORD")

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
    "Accept-Encoding": "identity",
    'Connection': 'keep-alive'
}

product_handler = None

file_name = "data.csv"
df = pd.DataFrame()
with open(file_name, mode='a', encoding='utf-8', newline='') as file:
    df = pd.read_csv(file_name)

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
        counter = 0

        for product in products:
            url = product.get('href')
            if url:
                full_url = f"{website_url}{url}" if not url.startswith("http") else url
                try:
                    product_data = collect_product_page(full_url)

                    counter += 1
                    log.info(f"Зібрано продуктів: {counter}/{product_count} з категорії {category}. \n Дані продукту: {product_data}")

                    if product_data:
                        if product_data["sku"] and product_data["reviews"]:
                            # Знаходимо product_id за SKU
                            try:
                                parent_series = df.loc[df['SKU'] == product_data["sku"], 'Parent']
                                if parent_series.empty:
                                    raise ValueError(f"SKU {product_data['sku']} не знайдено у data.csv")

                                parent_value = parent_series.iloc[0]
                                # Очікується формат схожий на "id:123", тому перетворюємо в рядок і видаляємо префікс
                                parent_str = str(parent_value).replace("id:", "").strip()
                                product_id = int(parent_str)

                                import_reviews_for_product(product_data["reviews"], product_id)
                            except Exception as e:
                                log.error(f"Не вдалося знайти product_id для SKU {product_data['sku']}: {e}")
                        else:
                            log.info(f"Пропускаємо продукт {full_url} через відсутність SKU або відгуків.")



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
    
    main_sku_element = soup.select_one(VARIATION_SKU_SELECTOR)
    if main_sku_element:
        main_sku = main_sku_element.get_text(strip=True).replace("SKU:", "").strip()

    # Отримання відгуків
    reviews_url = f"https://api.reviews.io/timeline/data?type=product_review&store=tower&sort=date_desc&page=1&per_page=15&include_sentiment_analysis=true&widget=polaris&sku={main_sku}&lang=en&enable_avatars=true&include_subrating_breakdown=1"
    reviews = []
    try:
        reviews_response = requests.get(reviews_url, headers=HEADERS)
        reviews_response.raise_for_status()
        reviews_data = reviews_response.json()
        for review in reviews_data.get("timeline", []):
            reviews.append({
                "reviewer": review.get("_source", {}).get("author"),
                "rating": review.get("_source", {}).get("rating"),
                "review": review.get("_source", {}).get("comments"),
                "reviewer_email": "anonymous@gmail.com",
                "status": "approved"
            })
    except Exception as e:
        log.error(f"Не вдалося отримати відгуки для продукту {url}: {e}")

    print(f"Знайдено відгуків: {len(reviews)} для продукту")

    return {
        "url": url,
        "sku": main_sku,
        "reviews": reviews
    }

def import_reviews_for_product(reviews, product_id):
    reviews_payload = {
        "create": []
    }

    for review in reviews:
        reviews_payload["create"].append({
            "product_id": product_id,
            "reviewer": review["reviewer"],
            "reviewer_email": review["reviewer_email"],
            "review": review["review"],
            "rating": review["rating"],
            "status": review["status"]
        })

    # Виклик обробника для імпорту відгуків
    if reviews_payload["create"]:
        reviews_res = make_request(
            "POST",
            f"{WC_URL}/wp-json/wc/v3/products/reviews/batch",
            auth=(WC_KEY, WC_SECRET),
            json=reviews_payload
        )

        if reviews_res.status_code not in [200, 201]:
            log.error(f"❌ Відгуки не додано: {reviews_res.status_code} {reviews_res.text}")
        else:
            created_reviews = reviews_res.json().get("create", [])
            print(reviews_res.json())
            print(reviews_res.headers)
            log.info(f"✅ Відгуків додано: {len(created_reviews)}")

# Функція для виконання HTTP запитів з повторними спробами
def make_request(method, url, **kwargs):
    for attempt in range(max_retries):
        if attempt > 0:
            log.warning(f"🔁 Повторна спроба {attempt+1} для {method.upper()} {url} через {error_delay} секунд")
            time.sleep(error_delay)
        else:
            time.sleep(requests_delay)
        try:
            response = requests.request(method, url, **kwargs)

            if "Fatal error" in response.text:
                log.error(f"❌ WC Fatal error: {response.text[:200]}...")
                continue

            if response.status_code in [200, 201]:
                return response

            log.error(f"❌ Спроба {attempt+1}: {response.status_code} {response.text[:200]}...")

        except Exception as e:
            log.error(f"❌ Виняток при запиті (спроба {attempt+1}): {e}")

    log.error(f"❌ Не вдалося виконати {method.upper()} {url} після 3 спроб")
    return None
    
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

    def test_handler(product):
        log.info(f"Обробка продукту: {product['url']}")

    # Збір та імпорт даних
    collect_products_from_categories(categories, test_handler)

    log.info("Процес збору та імпорту даних завершено.")

if __name__ == "__main__":
    main()
