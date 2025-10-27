# Встановлення і запуск

## Завантаження проекту на сервер

```bash
# Завантаження всього проекту (Скрипт запускаємо з пк)
scp -r /path/to/parser-importer username@server_ip:/path/to/destination/
```

## Встановлення залежностей

Підключіться до сервера та встановіть необхідні Python пакети:

```bash
ssh username@server_ip
cd /path/to/project/
pip install -r requirements.txt
```

## Налаштування конфігурації

1. Відкрийте файл .env в nano

```bash
cp .env.example .env
nano .env
```

2. Налаштування:
```
WC_URL=https://your-site.com
WC_KEY=your_consumer_key
WC_SECRET=your_consumer_secret
WC_USERNAME=your_wp_username
WC_PASSWORD=your_wp_password
```

### Де взяти WC_KEY і WC_SECRET

1) Зайдіть у адмін-панель шопу
2) Перейдіть до WooCommerce > Settings > Advanced > REST API
3) Створіть новий ключ: Add key > Введіть будь-який текст в полі Description > Поставте в полі Permissions - Read/Write > Generate API key
4) На сторінці відобразяться два значення Consumer key та Consumer secret це і є WC_KEY і WC_SECRET

### Де взяти WC_USERNAME та WC_PASSWORD

1) Зайдіть у адмін-панель шопу
2) Перейдіть до розділу Users
3) Оберіть свій акаунт
4) Прокрутіть до розділу Application Passwords
5) Створіть новий пароль: введіть будь-яке ім'я паролю у полі New Application Password Name > Натисніть Add Application Password
6) Ім'я паролю та пароль який з'явиться на сторінці це і є WC_USERNAME та WC_PASSWORD

3. За необхідності відредагуйте config.ini:

```bash
nano config.ini
```

**PARSER**

1) `max_retries` - кількість спроб запиту до донора при невдачі
2) `requests_delay` - затримка між запитами в секундах
3) `error_delay` - затримка перед повторною спробою при помилці в секундах
4) `batch_size` - товари імпортують пачками. Для прикладу якщо розмір пачки 5, то спочатку спарситься 5 товарів, а потім ці 5 товарів заливаються на WooCommerce. Це зроблено для збільшення продуктивності

**IMPORTER**

1) `download_images_before_import` - чи потрібно завантажувати картинки перед заливанням їх на WC чи заливати тільки посилання на ці картинки. True - так, False - ні. Корисно коли WC не може самостійно завантажити картинки
2) `requests_delay` - затримка між запитами до WC в секундах
3) `error_delay` - затримка перед повторною спробою при помилці в секундах
4) `max_retries` - максимальна к-сть спроб запиту до WC при помилках
5) `default_swatches_size` - розмір іконок у плагіні Swatches у пікселях

## Підготовка WordPress/WooCommerce

1. Додати функції в functions.php
   1) Скопіюйте вміст файлу [`functions.php`](functions.php)
   2) Зайдіть в адмін-панель
   3) Перейдіть у Appearance > Theme File Editor > functions.php
   4) Вставте скопійований код після наявного. УВАГА! Перевірте чи не дублюється код

## Підготовка категорій

Додайте URL категорій для парсингу у файл [`data/categories.json`](data/categories.json):

```json
[
  "https://www.towerhousewares.co.uk/toasters",
  "https://www.towerhousewares.co.uk/kettles",
  "https://www.towerhousewares.co.uk/air-fryers"
]
```

## Запуск парсера

```bash
cd src
python main.py
```

# Хід парсингу та імпорту

## Етапи роботи скрипта

1. **Ініціалізація**
   - Скрипт завантажує налаштування з [`config.ini`](config.ini) та категорії з [`data/categories.json`](data/categories.json)
   - Використовується функція [`collect_products_from_categories`](src/parser.py) для парсингу та [`import_batch`](src/importer.py) для імпорту

2. **Обробка категорій**
   Для кожної категорії скрипт:
   - Переходить по сторінках товарів
   - Збирає посилання на товари
   - Парсить дані кожного товару
   - Перевіряє чи товар вже імпортований через [`data/status.csv`](data/status.csv)

3. **Батчевий імпорт**
   - Коли накопичується батч товарів (розмір визначається в config.ini - `batch_size`), відбувається імпорт до WooCommerce
   - Створюються атрибути (колір, розмір)
   - Завантажуються зображення
   - Створюються варіації товарів
   - Встановлюються swatches для кольорів

## Індикатори прогресу

Під час роботи ви побачите кілька прогрес-барів:

1. **Прогрес імпорту батчу товарів**
   - Опис: Підготовка даних батчу для імпорту
   - Одиниця: т. (товари)
   - Значення: оброблено товарів / загальна кількість у батчі

```
Імпорт батчу товарів: 60%|██████    | 3/5 т.
```

2. **Прогрес завантаження зображень**
   - Опис: Завантаження зображень до WordPress
   - Одиниця: зображення
   - Значення: завантажено / загальна кількість

```
Завантаження зображень: 80%|████████  | 4/5 зображень
```

3. **Прогрес імпорту варіацій**
   - Опис: Створення варіацій товарів у WooCommerce
   - Одиниця: в. (варіації)
   - Значення: створено варіацій / загальна кількість

```
Імпорт варіацій батчу: 40%|████      | 2/5 в.
```

## Збереження прогресу

Скрипт автоматично зберігає інформацію про імпортовані товари у файлі [`data/status.csv`](data/status.csv):
```csv
SKU,Name
T20038BLK,Cavaletto 1.7L Glass Kettle
T20039RG,Bottega 2 Slice Toaster
```
При наступному запуску товари з цими SKU будуть пропущені.

# Модулі

Проект складається з кількох взаємопов'язаних модулів, кожен з яких відповідає за певну функціональність.

## src/main.py
Точка входу в програму, яка координує роботу всіх компонентів.

**Функціональність:**
- Завантаження списку категорій з [`data/categories.json`](data/categories.json)
- Ініціалізація процесу парсингу через [`collect_products_from_categories`](src/parser.py)
- Передача батчів товарів до імпортера через [`import_batch`](src/importer.py)

## src/parser.py
Основний модуль для збору даних з сайту Tower Housewares. Містить всю логіку парсингу товарів, категорій та їх варіацій.

### Функції:

1. **[`collect_products_from_categories(categories, handler)`](src/parser.py)** - Головна функція модуля:
   - Ітерує через категорії
   - Викликає [`collect_category`](src/parser.py) для кожної категорії
   - Передає батчі до обробника

2. **[`collect_category(category)`](src/parser.py)** - Збір товарів з окремої категорії:
   - Пагінація сторінок категорій (з `?limit=192` для зменшення кількості запитів)
   - Збір посилань на товари через `PRODUCT_LINK_SELECTOR`
   - Обробка батчів розміром `batch_size`
   - Підрахунок доступних та недоступних товарів

3. **[`collect_product_page(url)`](src/parser.py)** - Парсинг окремої сторінки товару:
   - Витягування основних даних: назва, ціна, опис, бренд
   - Перевірка чи товар вже імпортований через [`status_df`](src/parser.py)
   - Обробка варіацій товару (кольори через JavaScript парсинг)
   - Збір зображень через `IMAGES_SELECTOR`
   - Парсинг категорій через `CATEGORIES_SELECTOR`
   - Витягування SKU, наявності, цін

4. **Допоміжні функції:**
   - `extract_price(text)` - очищення та конвертація цін
   - `get_variation(variation_url, color_name)` - парсинг окремої варіації товару

### Налаштування:
Налаштування парсера (з [`config.ini`](config.ini)):
- `max_retries` = 3 - кількість спроб при невдачі
- `requests_delay` = 1 - пауза між запитами (сек)
- `error_delay` = 60 - пауза перед повторною спробою при помилці (сек)
- `batch_size` = 100 - розмір батчу товарів

### Селектори:
Основні CSS-селектори визначені як константи:
- `PRODUCT_LINK_SELECTOR` - посилання на товари в категорії
- `NEXT_PAGE_SELECTOR` - кнопка наступної сторінки
- `TITLE_SELECTOR` - назва товару
- `PRICE_SELECTOR` - ціна товару
- `DESCRIPTION_SELECTOR` - опис товару
- `VARIATION_SELECTOR` - опції варіацій
- `IMAGES_SELECTOR` - зображення товару
- `CATEGORIES_SELECTOR` - breadcrumb категорій

## src/importer.py
Модуль відповідає за завантаження спарсених даних до WooCommerce через REST API.

### Функції:

1. **[`import_batch(products)`](src/importer.py)** - Головна функція імпорту батчу товарів:
   - Підготовка даних для WooCommerce API
   - Створення атрибутів та термінів
   - Завантаження зображень (опційно)
   - Створення товарів (variable або simple)
   - Створення варіацій для товарів з кольорами
   - Оновлення [`data/status.csv`](data/status.csv)

2. **[`ensure_terms_exist(attr_id, terms)`](src/importer.py)** - Перевірка та створення термінів атрибутів:
   - Пошук існуючих термінів через API (пагінація по 100)
   - Створення нових термінів при необхідності
   - Додавання HEX-кодів для кольорів через [`webcolors`](src/importer.py) та custom REST API endpoint. УВАГА! Через обмеження бібліотеки webcolors у Wordpress неможливо додати всі існуючі кольори, кольори такі як latte чи cream і т.д. треба задавати вручну в адмінці

3. **[`upload_image_to_wc(image_url, session, max_attempts)`](src/importer.py)** - Завантаження зображень до медіатеки WordPress:
   - Фільтрація тільки webp зображень
   - Скачування зображення з URL
   - Валідація розміру (мінімум 200 байт)
   - Завантаження через `/wp/v2/media` API endpoint
   - Повторні спроби при невдачі

4. **[`get_or_create_category_chain(breadcrumb_string)`](src/importer.py)** - Створення ієрархії категорій:
   - Парсинг breadcrumb рядка (розділювач ">")
   - Рекурсивне створення батьківських категорій
   - Обробка символу `&` (заміна на `&amp;`)
   - Повернення ID кінцевої категорії
   - Кешування останніх 2 категорій для зменшення запитів

5. **[`make_request(method, url, **kwargs)`](src/importer.py)** - HTTP-клієнт з обробкою помилок:
   - Повторні спроби до `max_retries`
   - Затримка між запитами `requests_delay`
   - Обробка "Fatal error" від WooCommerce
   - Логування помилок

6. **[`get_attribute_id_by_slug(slug)`](src/importer.py)** - Отримання ID атрибуту за slug:
   - Запит списку атрибутів через API
   - Пошук за slug (наприклад, "pa_color", "pa_size")

### Налаштування:
Налаштування імпортера (з [`config.ini`](config.ini)):
- `download_images_before_import` = true - попереднє завантаження зображень
- `requests_delay` = 1 - затримка між запитами до WC (сек)
- `error_delay` = 5 - затримка перед повторною спробою при помилці (сек)
- `max_retries` = 3 - максимальна к-сть спроб
- `default_swatches_size` = 32 - розмір іконок swatches

### Особливості імпорту:

**Структура товару:**
- Variable products для товарів з варіаціями (кольорами)
- Simple products для товарів без варіацій
- Атрибути: pa_color (з swatches)
- Meta data для swatches (wcboost_variation_swatches)

**Swatches:**
- Для кожного кольору створюється термін
- HEX-код визначається через [`webcolors.name_to_hex`](src/importer.py)
- Встановлюється через custom REST API endpoint `/custom/v1/set-color-meta/`
- Зображення варіацій використовуються як іконки swatches

**Оптимізація:**
- Кешування останніх 2 категорій
- Пакетне створення товарів через `/products/batch`
- Пакетне створення варіацій через `/products/{id}/variations/batch`
- Завантаження зображень з прогрес-баром

## src/utils/log.py
Модуль для ініціалізації та налаштування логування.

### Функції:

**[`init_logger(name, level)`](src/utils/log.py)** - Ініціалізація логера:
- Створення унікального логера за ім'ям
- Файловий handler у [`logs/`](logs/) директорії
- Консольний handler для виводу в термінал
- Формат: `%(asctime)s - %(levelname)s - %(message)s`
- Кодування UTF-8 для підтримки української мови
- Запобігання дублюванню handlers

## functions.php
PHP-функції для WordPress, які забезпечують додаткову функціональність.

### REST API Endpoint:

**`/custom/v1/set-color-meta/`** - Встановлення HEX-коду для терміну кольору:
- Метод: POST
- Параметри: `term_id`, `hex`
- Встановлює meta: `_wcboost_variation_swatches_color` та `swatches_color`
- Доступ: тільки для користувачів з правами `edit_products`

## Взаємодія модулів

1. [`main.py`](src/main.py) завантажує категорії з [`data/categories.json`](data/categories.json)
2. [`main.py`](src/main.py) запускає [`collect_products_from_categories`](src/parser.py)
3. [`parser.py`](src/parser.py) парсить товари та передає батчі до [`import_batch`](src/importer.py)
4. [`importer.py`](src/importer.py) обробляє батчі та створює товари в WooCommerce
5. [`log.py`](src/utils/log.py) забезпечує логування на всіх етапах
6. Прогрес зберігається у [`data/status.csv`](data/status.csv) для запобігання дублюванню

## Структура проекту

```
parser-importer/
├── src/
│   ├── main.py              # Точка входу
│   ├── parser.py            # Парсинг донора
│   ├── importer.py          # Імпорт до WooCommerce
│   └── utils/
│       └── log.py           # Система логування
├── data/
│   ├── categories.json      # Список категорій для парсингу
│   └── status.csv           # Статус імпортованих товарів
├── logs/                    # Файли логів
├── config.ini               # Налаштування парсера та імпортера
├── .env                     # Креденшали WooCommerce
├── functions.php            # PHP-функції для WordPress
├── requirements.txt         # Python залежності
└── README.md                # Документація
```