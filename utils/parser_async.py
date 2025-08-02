import json
import configparser
from bs4 import BeautifulSoup
import re
import asyncio
from itertools import cycle
from tqdm import tqdm
import aiohttp
from aiohttp import ClientTimeout

# Завантажуємо конфігурацію
config = configparser.ConfigParser()
config.read('config.ini')

# Отримуємо налаштування з конфігурації
use_proxy = config.getboolean('PARSER', 'use_proxy', fallback=False)
max_threads = config.getint('PARSER', 'max_threads', fallback=5)
max_retries = config.getint('PARSER', 'max_retries', fallback=3)
requests_delay = config.getint('PARSER', 'requests_delay', fallback=1)
batch_size = config.getint('PARSER', 'batch_size', fallback=100)

# Якщо використовується проксі, завантажуємо список проксі з файлу
if use_proxy:
    with open('proxies.txt', 'r', encoding='utf-8') as f:
        proxies = [line.strip() for line in f if line.strip()]
    proxy_cycle = cycle(proxies)
else:
    proxy_cycle = None

sem = asyncio.Semaphore(max_threads)

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
AVAILABILITY_SELECTOR = ".Product__BuyBox strong"
IMAGES_SELECTOR = "button.js-gallery-thumb"
IMAGE_SELECTOR = "#main .Product .Product__Top .Product__Gallery .ProductGallery.js-hover-zoom img"
CATEGORIES_SELECTOR = ".Product__Top li.breadcrumb-item a"
VARIATION_SELECTOR = ".custom-select option"
SIZE_SELECTOR = ".Product__Details .Product__Title label[for='Size'] span"
COLOR_SELECTOR = ".Product__Details .Product__Title label[for='Colour'] span"

# Заголовки для HTTP-запитів
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive'
}

# Асинхронна функція для отримання HTML-коду сторінки
async def fetch(session, url):
    for attempt in range(max_retries):
        proxy = next(proxy_cycle) if proxy_cycle else None
        try:
            async with sem:
                async with session.get(url, proxy=proxy) as response:
                    response.raise_for_status()
                    text = await response.text()
                await asyncio.sleep(requests_delay)
            return text
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"❌ Не вдалося отримати {url}: {e}")
            await asyncio.sleep(requests_delay)
    return None

# Асинхронна функція для отримання HTML-коду сторінки варіації
async def variation_fetch(session, url):
    for attempt in range(max_retries):
        proxy = next(proxy_cycle) if proxy_cycle else None
        try:
            async with session.get(url, proxy=proxy) as response:
                response.raise_for_status()
                text = await response.text()
            return text
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"❌ Не вдалося отримати {url}: {e}")
    return None

# Асинхронна функція для збору даних про продукти з категорій
async def collect_product_data(categories, product_handler):
    async with aiohttp.ClientSession(headers=HEADERS, timeout=ClientTimeout(total=None)) as session:
        # Прогресбар для відстеження прогресу
        for category in tqdm(categories, desc='Категорії', unit='категорія'):
            try:
                await collect_category(session, category, product_handler)
            except Exception as e:
                print(f"Помилка при зборі даних для категорії {category}: {e}")
                await asyncio.sleep(requests_delay)

# Функція для збору даних з категорії
async def collect_category(session, category, product_handler):
    page_url = category + "?pageSize=128"

    last_page_number = None
    page_bar = None

    batch = []

    # Цикл для збору продуктів з категорії по сторінках
    while True:
        page_html = await fetch(session, page_url)
        if page_html is None:
            print(f"❌ Не вдалося отримати HTML для {page_url}")
            break
        soup = BeautifulSoup(page_html, 'html.parser')

        # Знаходимо останню сторінку, якщо вона є
        if not last_page_number:
            last_page_element = soup.select_one(LAST_PAGE_SELECTOR)
            last_page_number = int(last_page_element.get_text(strip=True))
            page_bar = tqdm(total=last_page_number, desc='Сторінки', unit='стр.')
        
        # Оновлюємо прогресбар для сторінок
        if page_bar:
            page_bar.update(1)
        
        # Збираємо посилання на продукти на поточній сторінці
        products = soup.select(PRODUCT_LINK_SELECTOR)

        # Якщо продукти не знайдено, виходимо з циклу
        if not products:
            print(f"❌ Не знайдено продукти на сторінці {page_url}")
            break

        # Збираємо дані про кожен продукт
        for product in tqdm(products, desc="Товари на сторінці", unit="прод"):
            url = product.get('href')
            if url:
                full_url = "https://www.fruugo.co.uk" + url if url.startswith("/") else url
                product_data = await collect_product_page(session, full_url, page_url)
                if product_data:
                    batch.append(product_data)

                    # Якщо розмір батчу досягнув batch_size, обробляємо його
                    if len(batch) >= batch_size:
                        product_handler(batch)
                        batch = []

        # Перевірка наявності кнопки "Наступна сторінка"
        next_page = soup.select_one(NEXT_PAGE_SELECTOR)
        if not next_page or 'disabled' in next_page.get('class', []):
            print(f"❌ Наступна сторінка не знайдена або вона вимкнена.")
            break
        else:
            next_page_url = next_page.get('href')
            if next_page_url:
                page_url = "https://www.fruugo.co.uk" + next_page_url if next_page_url.startswith("/") else next_page_url
            else:
                print("❌ URL наступної сторінки не знайдено.")
                break

        await asyncio.sleep(requests_delay)

    # Обробка залишків продуктів у батчі
    if len(batch) > 0:
        product_handler(batch)
        

# Функція для збору даних про продукт за URL
async def collect_product_page(session, url, parent_page_url):
    html = await fetch(session, url)
    if html is None:
        return None
    soup = BeautifulSoup(html, 'html.parser')

    # Отримання заголовку
    title = soup.select_one(TITLE_SELECTOR)
    if title:
        title = title.get_text(strip=True)
    else:
        print(f"❌ Не вдалося знайти назву продукту на сторінці {url}")
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
            print(f"❌ Не вдалося знайти ціну продукту на сторінці {url}")
            return None

    # Отримання опису
    description = soup.select_one(DESCRIPTION_SELECTOR)
    if description:
        description = str(description)
    else:
        print(f"❌ Не вдалося знайти опис продукту на сторінці {url}")
        return None

    # Отримання категорії
    categories = soup.select(CATEGORIES_SELECTOR)
    if categories:
        categories = " > ".join([cat.get_text(strip=True) for cat in categories])
    else:
        print(f"❌ Не вдалося знайти категорії продукту на сторінці {url}")
        categories = None

    # Отримання бренду
    brand = soup.select_one(BRAND_SELECTOR)
    if brand:
        brand = brand.get_text(strip=True)
    else:
        brand = None

    # Функція для отримання варіації за URL
    async def get_variation_by_url(variation_url):
        match = re.search(r'/p-(\d+)-(\d+)', variation_url)
        if match:
            product_id, variant_id = match.groups()
            sku = f"SKU-{product_id}-{variant_id}"
        else:
            print(f"❌ Не вдалося отримати ID продукту з URL: {variation_url}")
            return None

        html = await variation_fetch(session, variation_url)
        if html is None:
            return None
        soup = BeautifulSoup(html, 'html.parser')

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

        # Костиль для обміну розміру та кольору - на сайті коли вони обидва присутні, то розмір і колір переплутані
        if color and size:
            new_color = size
            new_size = color
            size = new_size
            color = new_color

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
    images = []
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

            try:
                variation_data = await get_variation_by_url(variation_url)
            except Exception as e:
                print(f"❌ Помилка при отриманні варіації з {variation_url}: {e}")
                continue
            if variation_data:
                variations.append(variation_data)
                if variation_data.get("images"):
                    for img in variation_data["images"]:
                        if img not in images:
                            images.append(img)


    product_data = {
        "title": title,
        "url": url,
        "parent_page_url": parent_page_url,
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

    counter = 0

    def test_handler(data):
        global counter
        file_path = f"data/batches/batch_{counter}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        counter += 1

    asyncio.run(collect_product_data(categories, test_handler))