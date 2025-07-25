import requests
from bs4 import BeautifulSoup
import json
import re

TITLE_SELECTOR = ".Product__Details h1.js-product-title"
PRICE_SELECTOR = ".js-meta-price"
REGULAR_PRICE_SELECTOR = ".Product__Details .Product__Price del"
SALE_PRICE_SELECTOR = ".js-meta-price"
DESCRIPTION_SELECTOR = "#description"
BRAND_SELECTOR = "ul.product-description-spec-list li:has(strong:-soup-contains('Brand')) span"

VARIATION_SELECTOR = ".custom-select option"

# На сайті переплутані селектори для розмірів та кольорів, тому використовуємо різні селектори
SIZE_SELECTOR = ".Product__Details .Product__Title label[for='Colour'] span"
COLOR_SELECTOR = ".Product__Details .Product__Title label[for='Size'] span"
AVAILABILITY_SELECTOR = ".Product__BuyBox strong"
IMAGES_SELECTOR = "button.js-gallery-thumb"
IMAGE_SELECTOR = "#main .Product .Product__Top .Product__Gallery .ProductGallery.js-hover-zoom img"

# Функція для отримання даних продукту за URL
def get_product_data(url):
    try:
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
            "brand": brand,
            "variations": variations,
        }
        return product_data
    except requests.RequestException as e:
        print(f"Помилка при отриманні даних продукту з {url}: {e}")
        return None
    
# Приклад використання
if __name__ == "__main__":
    url = "https://www.fruugo.co.uk/vintage-marlboro-cowboy-wild-west-shirt-country-music-shirt-cowboy-killer-shirt-boho-shirt-cowboy-rodeo-tshirt-counfctfw163/p-384552544"
    product_data = get_product_data(url)
    if product_data:
        print(json.dumps(product_data, ensure_ascii=False, indent=2))