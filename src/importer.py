import os
import json
import time
import threading
from pathlib import Path
from queue import Queue
from dotenv import load_dotenv
import threading
import requests
from urllib.parse import urlparse
from io import BytesIO
import configparser
from tqdm import tqdm
import webcolors
from rapidfuzz import process
import pandas as pd

# Отримуємо налаштування з конфігурації
config = configparser.ConfigParser()
config.read('config.ini')

# Параметри з конфігурації
max_retries = config.getint('IMPORTER', 'max_retries', fallback=3)
download_images_before_import = config.getboolean('IMPORTER', 'download_images_before_import', fallback=True)
requests_delay = config.getint('IMPORTER', 'requests_delay', fallback=1)
error_delay = config.getint('IMPORTER', 'error_delay', fallback=5)
default_swatches_size = config.getint('IMPORTER', 'default_swatches_size', fallback=32)

# Завантажуємо .env
load_dotenv()
WC_URL = os.getenv("WC_URL")
WC_KEY = os.getenv("WC_KEY")
WC_SECRET = os.getenv("WC_SECRET")
WC_USERNAME = os.getenv("WC_USERNAME")
WC_PASSWORD = os.getenv("WC_PASSWORD")

# Флаг для контролю процесу обробки
is_processing = False

# Зчитуємо статус файл, якщо він існує, якщо ні - створюємо порожній DataFrame
try:
    status_df = pd.read_csv('data/status.csv')
except (FileNotFoundError, pd.errors.EmptyDataError):
    status_df = pd.DataFrame(columns=["SKU", "Name"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
    "Accept-Language": "en-US,en;q=0.5",
}

# Функція для виконання HTTP запитів з повторними спробами
def make_request(method, url, **kwargs):
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"🔁 Повторна спроба {attempt+1} для {method.upper()} {url} через {error_delay} секунд")
            time.sleep(error_delay)
        else:
            time.sleep(requests_delay)
        try:
            response = requests.request(method, url, **kwargs)

            if "Fatal error" in response.text:
                print(f"❌ WC Fatal error: {response.text[:200]}...")
                continue

            if response.status_code in [200, 201]:
                return response

            print(f"❌ Спроба {attempt+1}: {response.status_code} {response.text[:200]}...")

        except Exception as e:
            print(f"❌ Виняток при запиті (спроба {attempt+1}): {e}")

    print(f"❌ Не вдалося виконати {method.upper()} {url} після 3 спроб")
    return None

# Отримання ID атрибуту за slug
def get_attribute_id_by_slug(slug):
    response = make_request(
        "GET",
        f"{WC_URL}/wp-json/wc/v3/products/attributes",
        auth=(WC_KEY, WC_SECRET)
    )

    attributes = response.json()

    for attr in attributes:
        if attr["slug"] == slug:
            return attr["id"]

    raise ValueError(f"⚠️ Атрибут зі slug '{slug}' не знайдено.")

color_id = get_attribute_id_by_slug("pa_color")
size_id = get_attribute_id_by_slug("pa_size")

# Функція для імпорту батчу
def import_batch(products):
    create_payload = {
        "create": []
    }

    all_img_urls = {}
    last_categories = {}

    # Формуємо дані для створення товарів
    for p in tqdm(products, desc="Імпорт батчу товарів", unit="т."):
        # Імпорт варіацій
        attributes = []
        img_urls = {}

        # Перевірка наявності атрибутів кольору та розміру
        def ensure_terms_exist(attr_id, terms):
            page = 1

            existing_names = {}

            while True:
                r = requests.get(
                    f"{WC_URL}/wp-json/wc/v3/products/attributes/{attr_id}/terms",
                    auth=(WC_KEY, WC_SECRET),
                    params={"per_page": 100, "page": page}
                )

                data = r.json()
                if not data:
                    break

                existing_names.update({t['name']: t['id'] for t in data})

                if len(data) < 100:
                    break

                page += 1

            terms_ids = {}

            for term in terms:
                term_id = existing_names.get(term)
                if term_id:
                    terms_ids[term] = term_id

                if not term_id:
                    r = requests.post(
                        f"{WC_URL}/wp-json/wc/v3/products/attributes/{attr_id}/terms",
                        auth=(WC_KEY, WC_SECRET),
                        json={"name": term}
                    )
                    if r.status_code != 201:
                        print(f"⚠️ Не вдалося створити термін '{term}': {r.status_code} - {r.text}")
                        continue
                    term_id = r.json().get("id")

                if attr_id == color_id and term_id:
                    hex_code = webcolors.name_to_hex(term)
                    if hex_code:
                        r = requests.post(
                            f"https://shop1.sweetcare.christmas/wp-json/custom/v1/set-color-meta/",
                            json={"term_id": term_id, "hex": hex_code}
                        )
                    else:
                        print(f"⚠️ Не вдалося визначити HEX для '{term}'")

            return terms_ids

        # Обробка розмірів ( в цьому донорі розміри не використовуються )
        # sizes = list(dict.fromkeys(v["size"] for v in p["variations"] if v.get("size")))
        # if sizes:
        #     sizes_ids = ensure_terms_exist(size_id, sizes)
        #     attributes.append({
        #         "id": size_id,
        #         "name": "size",
        #         "variation": True,
        #         "visible": True,
        #         "options": sizes
        #     })

        # Обробка кольорів
        colors = list(dict.fromkeys(v["color"] for v in p["variations"] if v.get("color")))
        if colors:
            colors_term_ids = ensure_terms_exist(color_id, colors)
            attributes.append({
                "id": color_id,
                "name": "color",
                "variation": True,
                "visible": True,
                "options": colors
            })
        
        # Завантаження зображень
        if download_images_before_import:
            for img_url in tqdm(p["images"], desc="Завантаження зображень", leave=False):
                uploaded = upload_image_to_wc(img_url)
                if uploaded:
                    img_urls[img_url] = uploaded
        else:
            img_urls = {img: img for img in p["images"]}

        # Додаємо всі зображення до all_img_urls
        for img_url, img_id in img_urls.items():
            all_img_urls[img_url] = img_id

        # Отримання категорії
        if p["categories"] in last_categories:
            category_id = last_categories[p["categories"]]
            print(f"🔄 Використання останньої категорії: {p['categories']} (ID: {category_id})")
        else:
            category_id = get_or_create_category_chain(p["categories"])

        # Зберігаємо останні категорії щоб зменшити кількість запитів
        last_categories[p["categories"]] = category_id

        # Обмежуємо кількість збережених останніх категорій до 2
        if len(last_categories) > 2:
            last_categories = {k: last_categories[k] for k in list(last_categories.keys())[-2:]}

        swatches = {}
        for var in p["variations"]:
            if var.get("color") and var.get("images"):
                color_name = var["color"]
                color_term_id = colors_term_ids.get(color_name)
                if color_term_id:
                    swatches[str(color_term_id)] = {"image": str(img_urls.get(var["images"][0], ""))}

        if swatches:
            meta_data = [
                {
                    "key": "wcboost_variation_swatches",
                    "value": {
                        "pa_color": {
                            "type": "image",
                            "shape": "square",
                            "size": "custom",
                            "custom_size": {"width": default_swatches_size, "height": default_swatches_size},
                            "swatches": swatches
                        }
                    }
                }
            ]

            create_payload["create"].append({
                "name": p["title"],
                "type": "variable",
                "description": p["description"],
                "categories": [{"id": category_id}],
                "regular_price": str(p["regular_price"]),
                "sale_price": str(p["sale_price"]),
                "images": [{"id": img} for img in img_urls.values()],
                "attributes": attributes,
                "meta_data": meta_data
            })
        else:
            create_payload["create"].append({
                "name": p["title"],
                "type": "simple",
                "description": p["description"],
                "regular_price": str(p["regular_price"]),
                "sale_price": str(p["sale_price"]),
                "categories": [{"id": category_id}],
                "images": [{"id": img} for img in img_urls.values()],
                "attributes": attributes,
            })

    # Створення товарів у WooCommerce
    product_res = make_request(
        "POST",
        f"{WC_URL}/wp-json/wc/v3/products/batch",
        auth=(WC_KEY, WC_SECRET),
        json=create_payload
    )

    # Перевірка статусу відповіді
    if product_res.status_code not in [200, 201]:
        print(f"❌ Помилка при створенні товарів: {product_res.status_code} {product_res.text}")
        return

    # Отримання створених товарів
    created = product_res.json().get("create", [])
    print(f"✅ Створено товарів: {len(created)}")

    # Імпорт варіацій для кожного створеного товару
    for product_obj, p in tqdm(zip(created, products), total=len(created), desc="Імпорт варіацій батчу", unit="в."):
        product_id = product_obj["id"]
        variations = []

        for v in p["variations"]:
            attr = []
            if v.get("size"):
                attr.append({"id": size_id, "name": "size", "option": v["size"]})
            if v.get("color"):
                attr.append({"id": color_id, "name": "color", "option": v["color"]})

            variations.append({
                "sku": v["sku"],
                "regular_price": str(p["regular_price"]),
                "sale_price": str(p["sale_price"]),
                "attributes": attr,
                "in_stock": v["availability"],
                "image": (
                    {"id": all_img_urls.get(v["images"][0])}
                    if v.get("images") and v["images"][0] in all_img_urls
                    else {}
                ),
            })

        var_res = make_request(
            "POST",
            f"{WC_URL}/wp-json/wc/v3/products/{product_id}/variations/batch",
            auth=(WC_KEY, WC_SECRET),
            json={"create": variations}
        )

        if var_res.status_code not in [200, 201]:
            print(f"❌ Варіації для продукту ID {product_obj.get('id', 'невідомо')} не додано: {var_res.status_code}")
        else:
            print(f"  ↳ ✅ Варіацій додано: {len(variations)} для продукту ID {product_id}")
            # Оновлюємо статус продукту в статус файлі
            global status_df
            for v in p["variations"]:
                status_df = status_df.append({
                    "SKU": v["sku"],
                    "Name": p["title"]
                }, ignore_index=True)

    # Зберігаємо оновлений статус файл
    status_df.to_csv('data/status.csv', index=False)
    

# Функція для завантаження зображення до WooCommerce
def upload_image_to_wc(image_url, retries=max_retries):
    try:
        response = make_request("GET", image_url, headers=HEADERS)
        if not response or response.status_code != 200:
            print(f"❌ Помилка завантаження картинки: {image_url}")
            return None

        content = response.content

        if not content or len(content) < 100:
            print(f"❌ Порожній або надто малий файл: {image_url}")
            return None

        filename = Path(urlparse(image_url).path).name

        time.sleep(requests_delay)

        for attempt in range(retries):
            file_stream = BytesIO(content)
            headers = {
                'Content-Disposition': f'attachment; filename="{filename}"'
            }

            # Визначаємо тип файлу за розширенням
            ext = filename.split('.')[-1].lower()
            mime_types = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'webp': 'image/webp',
            }
            mime_type = mime_types.get(ext, 'application/octet-stream')

            res = requests.post(
                f"{WC_URL}/wp-json/wp/v2/media",
                auth=(WC_USERNAME, WC_PASSWORD),
                headers=headers,
                files={'file': (filename, file_stream, mime_type)}
            )

            if res and res.status_code in [200, 201]:
                try:
                    return res.json()["id"]
                except json.JSONDecodeError:
                    print(f"❌ Не вдалося розпарсити JSON відповідь: {res.text}.\n🔁 Повторна спроба...")
            else:
                print(f"❌ WC не прийняв картинку (спроба {attempt+1}): {res.status_code if res else '❌'} {res.text[:200] if res else ''}")
                time.sleep(error_delay)

        print(f"❌ Вичерпано спроб завантаження зображення для {image_url}")
        return None

    except Exception as e:
        print(f"❌ Виняток при завантаженні зображення: {e}")
        return None

# Функція для отримання або створення категорії з ланцюжком (breadcrumb)
def get_or_create_category_chain(breadcrumb_string):
    categories = [cat.strip() for cat in breadcrumb_string.split(">")]
    parent_id = 0
    final_id = None

    for cat in categories:
        cat = cat.replace("&", "&amp;")
        res = make_request(
            "GET",
            f"{WC_URL}/wp-json/wc/v3/products/categories",
            auth=(WC_KEY, WC_SECRET),
            params={"search": cat, "parent": parent_id}
        )

        if not res:
            print(f"❌ Не вдалося отримати категорії для '{cat}'")
            return None

        try:
            data = res.json()
        except Exception as e:
            print(f"❌ Некоректний JSON у відповіді: {res.text}")
            raise e
        cat_obj = next((c for c in data if c["name"].lower() == cat.lower()), None)

        if cat_obj:
            final_id = cat_obj["id"]
            parent_id = final_id
            continue

        new_res = make_request(
            "POST",
            f"{WC_URL}/wp-json/wc/v3/products/categories",
            auth=(WC_KEY, WC_SECRET),
            json={"name": cat, "parent": parent_id}
        )

        if not new_res:
            print(f"❌ Запит створення категорії '{cat}' не дав відповіді")
            return None

        new_cat = new_res.json()

        if "id" in new_cat:
            final_id = new_cat["id"]
            parent_id = final_id
        elif new_cat.get("code") == "term_exists":
            final_id = new_cat["data"]["resource_id"]
            parent_id = final_id
        else:
            print(f"❌ Помилка створення категорії '{cat}': {new_cat}")
            return None

    return final_id
