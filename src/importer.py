import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
import requests
from urllib.parse import urlparse
from io import BytesIO
import configparser
from tqdm import tqdm
import webcolors
import pandas as pd
from utils.log import init_logger
from uuid import uuid4

# Ініціалізуємо логер
log = init_logger(__name__)

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
            log.info(f"Знайдено ID атрибуту '{slug}': {attr['id']}")
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

                existing_names.update({t['name'].strip().lower(): t['id'] for t in data})

                if len(data) < 100:
                    break

                page += 1

            terms_ids = {}

            for term in terms:
                term_id = existing_names.get(term.strip().lower())
                if term_id:
                    terms_ids[term] = term_id

                if not term_id:
                    r = requests.post(
                        f"{WC_URL}/wp-json/wc/v3/products/attributes/{attr_id}/terms",
                        auth=(WC_KEY, WC_SECRET),
                        json={"name": term}
                    )
                    if r.status_code != 201:
                        log.warning(f"⚠️ Не вдалося створити термін '{term}': {r.status_code} - {r.text}")
                        continue
                    term_id = r.json().get("id")

                if attr_id == color_id and term_id:
                    try:
                        hex_code = webcolors.name_to_hex(term)
                    except ValueError:
                        hex_code = None
                    if hex_code:
                        r = requests.post(
                            f"https://shop1.sweetcare.christmas/wp-json/custom/v1/set-color-meta/",
                            json={"term_id": term_id, "hex": hex_code}
                        )
                    else:
                        log.warning(f"⚠️ Не вдалося визначити HEX для '{term}'")

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
            log.info(f"🔄 Використання останньої категорії: {p['categories']} (ID: {category_id})")
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
        log.error(f"❌ Помилка при створенні товарів: {product_res.status_code} {product_res.text}")
        return

    # Отримання створених товарів
    created = product_res.json().get("create", [])
    log.info(f"✅ Створено товарів: {len(created)}")

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
            log.error(f"❌ Варіації для продукту ID {product_obj.get('id', 'невідомо')} не додано: {var_res.status_code}")
        else:
            log.info(f"  ↳ ✅ Варіацій додано: {len(variations)} для продукту ID {product_id}")
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
def upload_image_to_wc(image_url, session=None, max_attempts=1, timeout=10):
    """
    Швидке завантаження тільки для webp-подібних URL (наприклад: .../webp/fit?...).
    Повертає ID медіа у WP або None.
    """
    try:
        # Просте правило: якщо в шляху немає 'webp' — вихід
        path = urlparse(image_url).path or ""
        if 'webp' not in path.lower():
            log.error("❌ URL не виглядає як webp — пропускаю: " + image_url)
            return None

        sess = session or requests.Session()
        get_headers = {'User-Agent': 'Mozilla/5.0 (ImageUploader/fast)'}
        r = sess.get(image_url, headers=get_headers, timeout=timeout, allow_redirects=True)

        if r.status_code != 200:
            log.error(f"❌ GET failed {r.status_code} for {image_url}")
            return None

        content_type = (r.headers.get('Content-Type') or '').lower()
        # Перевірка: має бути webp (або шлях містить webp — вже перевірено)
        if 'webp' not in content_type and 'webp' not in path.lower():
            log.error(f"❌ Content-Type не webp ({content_type}) — {image_url}")
            return None

        content = r.content
        if not content or len(content) < 200:
            log.error(f"❌ Файл занадто малий ({len(content)} байт): {image_url}")
            return None

        filename = f"{uuid4().hex}.webp"
        file_stream = BytesIO(content)
        file_stream.seek(0)

        wp_headers = {
            'Content-Disposition': f'attachment; filename="{filename}"'
        }

        for attempt in range(max_attempts):
            res = sess.post(
                f"{WC_URL}/wp-json/wp/v2/media",
                auth=(WC_USERNAME, WC_PASSWORD),
                headers=wp_headers,
                files={'file': (filename, file_stream, 'image/webp')},
                timeout=30
            )

            if res is not None and res.status_code in (200, 201):
                try:
                    return res.json().get('id')
                except Exception:
                    log.error("❌ Не вдалося розпарсити JSON з WP: " + (res.text or ""))
                    return None
            else:
                log.error(f"❌ Завантаження не вдалося (attempt {attempt+1}): {getattr(res,'status_code',None)} {getattr(res,'text','')[:200]}")
                # швидка спроба — не чекаємо
        return None

    except Exception as e:
        log.error(f"❌ Виняток: {e}")
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
            log.error(f"❌ Не вдалося отримати категорії для '{cat}'")
            return None

        try:
            data = res.json()
        except Exception as e:
            log.error(f"❌ Некоректний JSON у відповіді: {res.text}")
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
            log.error(f"❌ Запит створення категорії '{cat}' не дав відповіді")
            return None

        new_cat = new_res.json()

        if "id" in new_cat:
            final_id = new_cat["id"]
            parent_id = final_id
        elif new_cat.get("code") == "term_exists":
            final_id = new_cat["data"]["resource_id"]
            parent_id = final_id
        else:
            log.error(f"❌ Помилка створення категорії '{cat}': {new_cat}")
            return None

    return final_id

if __name__ == "__main__":
    test_batch = [
        {'title': 'Bottega 2 Slice Stainless Steel Toaster', 'url': 'https://www.towerhousewares.co.uk/toasters/rose-gold-2-slice-ss-toaster-2', 'regular_price': 44.99, 'sale_price': None, 'description': '<div class="squeeze-up tab-pane fade in active" id="description_0_1651566202983" role="tabpanel">\n<div class="row margin-0 push-down">\n<div class="col-xs-12">\n<div class="row"><div class="col-sm-12"><h2 style="text-align: center;">Bottega<span style="font-size: 2rem;">\xa0</span>2 Slice Stainless Steel Toaster</h2><h3 style="text-align: center;">From toast to bagels to crumpets, get toasting your favourite baked goods with ease\xa0</h3><p style="text-align: center;"><img src="https://images.shopcdn.co.uk/df/b8/dfb8505819643947b243cbe6f761fd0f/970x300/webp/resize"/></p><p style="text-align: center;"><strong>ADJUSTABLE BROWNING CONTROL</strong></p><p style="text-align: center;">Choose from a range of settings for bread, muffins, crumpets and bagels</p><p style="text-align: center;">\xa0</p><p style="text-align: center;"><strong>SELF-CENTRING FUNCTION</strong></p><p style="text-align: center;">Makes sure your food is toasted to a perfect consistency for delicious results</p><p style="text-align: center;">\xa0</p><p style="text-align: center;"><strong>DEFROST &amp; REHEAT</strong></p><p style="text-align: center;">Toast your food straight from frozen and ensure it is toasted to the perfect temperature</p><p style="text-align: center;">\xa0</p><p style="text-align: center;"><strong>EASY-TO-CLEAN</strong></p><p style="text-align: center;">Removable tray makes it easy to dispose of excess crumbs and keep your surfaces tidy</p><p style="text-align: center;">\xa0</p><p style="text-align: center;"><strong>CORD STORAGE</strong></p><p style="text-align: center;">Integrated cord storage keeps your kitchen free from messy, trailing wires</p><p style="text-align: center;">\xa0</p><p style="text-align: center;"><strong>ROSE GOLD COLLECTION</strong></p><p style="text-align: center;">For a contemporary designed kitchen, the look with the full Rose Gold range from Tower</p><p style="text-align: center;">\xa0</p><p style="text-align: center;"><strong>3 YEAR WARRANTY</strong></p><p style="text-align: center;">Comes with standard 1 year warranty and an additional 2 years when registering the product online within 28 days of purchase</p><p style="text-align: center;">\xa0</p><p style="text-align: center;">Be a toasting champion with the Tower Bottega rose gold 2 slice toaster. Featuring variable browning control that gives you precise toasting results that suits your taste. From loaves, bagels and crumpets, the self-centring function will consistently toast your items to perfection after every use. For more functionality, the toaster includes a defrost, reheat and cancel options for better control and convenience for toasting frozen snacks.</p><p style="text-align: center;">Including a removable tray for an easy clean and keeping your countertop crumb-free with a cord storage to keep surfaces wire-free. Finished with a black coating and rose gold accents, the Bottega toaster complements the look of your kitchen countertop.</p></div></div><div class="row"><div class="col-sm-4" style="text-align: center;"><img src="https://images.shopcdn.co.uk/74/04/74041b619022ce1782abcc5ff4bc038e/1350x1350/webp/resize"/></div><div class="col-sm-4" style="text-align: center;"><img src="https://images.shopcdn.co.uk/34/80/34800a52714daa461547e5b5e4f30cf3/1350x1350/webp/resize"/></div><div class="col-sm-4" style="text-align: center;"><img src="https://images.shopcdn.co.uk/6c/0f/6c0f5437b919e86442f09c82032cc9be/1350x1350/webp/resize"/></div></div> </div>\n</div>\n</div>', 'categories': 'Kitchen Appliances > Breakfast > Toasters', 'images': ['https://images.shopcdn.co.uk/d7/08/d70882899a8e5df964c048dcb93307f1/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/e5/97/e59735059b7e3a31707000fdd3c0de0b/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/44/33/443368dd1f5b66b722c9e35c5ba4464c/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/8c/ee/8cee066ed97da2b3de9e65109d0a18a3/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/41/3e/413ed613f5628e9733eddb843cbbe578/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/6f/aa/6faaabbb2416221789dfc25dd5173f5a/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/a7/f0/a7f04653881b7d41d9461f7739fb0929/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/e0/6e/e06e1d12c28568042115493f6def1241/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/82/32/82329b137abfbc8a3ee7ef366ef80cc8/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/62/fa/62fa8bcf335e52438deede91ff53452b/512x512/webp/fit?force=true'], 'brand': 'Tower', 'variations': [{'sku': 'T20016W', 'color': 'white', 'availability': False, 'images': ['https://images.shopcdn.co.uk/d7/08/d70882899a8e5df964c048dcb93307f1/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/e5/97/e59735059b7e3a31707000fdd3c0de0b/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/44/33/443368dd1f5b66b722c9e35c5ba4464c/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/8c/ee/8cee066ed97da2b3de9e65109d0a18a3/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/41/3e/413ed613f5628e9733eddb843cbbe578/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/6f/aa/6faaabbb2416221789dfc25dd5173f5a/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/a7/f0/a7f04653881b7d41d9461f7739fb0929/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/e0/6e/e06e1d12c28568042115493f6def1241/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/82/32/82329b137abfbc8a3ee7ef366ef80cc8/512x512/webp/fit?force=true', 'https://images.shopcdn.co.uk/62/fa/62fa8bcf335e52438deede91ff53452b/512x512/webp/fit?force=true']}]}
    ]
    import_batch(test_batch)