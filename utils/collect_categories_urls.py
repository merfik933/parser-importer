"""
Скрипт для автоматизованого збору URL категорій з сайту https://www.fruugo.co.uk/ за допомогою Selenium та undetected_chromedriver.
Основні етапи роботи:
- Відкриває головну сторінку магазину Fruugo.
- Закриває попередження про куки (якщо воно з'являється).
- Відкриває головне бічне меню та переходить до розділу "Shop by department".
- Рекурсивно обходить всі вкладені категорії, збираючи їх URL.
- Зберігає зібрані посилання у файл ./settings/categories.json у форматі JSON.

УВАГА! ДЛЯ СТАБІЛЬНОЇ РОБОТИ СКРИПТУ НЕОБХІДНО МАТИ ВСТАНОВЛЕНИЙ БРАУЗЕР GOOGLE CHROME ОСТАНОВЛЕНОЇ ВЕРСІЇ

Використання: 
запустіть скрипт напряму, попередньо підготувавши файл categories.json з посиланнями на категорії, або викличте collect_categories_urls() з іншого модуля.
"""

import json
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging

logging.basicConfig(level=logging.INFO)

def collect_categories_urls():
    """
    Збирає URL категорій з сайту Fruugo та зберігає їх у файл categories.json.
    Використовує Selenium для автоматизації браузера та обходу меню категорій.
    """
    # Налаштування браузера
    logging.info("Ініціалізація браузера...")
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")

    # Відриваємо браузер з використанням undetected_chromedriver
    driver = uc.Chrome(options=options)

    # Відкриття головної сторінки Fruugo
    logging.info("Відкриття головної сторінки fruugo.co.uk...")
    driver.get("https://www.fruugo.co.uk/")

    # Очікування завантаження сторінки та закриття попередження про куки
    logging.info("Очікування завантаження сторінки та закриття попередження про куки...")
    try:
        decline_cookies_button = WebDriverWait(driver, 60).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[aria-label='Cookie consent'] .button.button-orange"))
        )
        decline_cookies_button.click()
        logging.info("Попередження про куки закрито.")
    except Exception as e:
        logging.error(f"Не вдалося закрити попередження про куки: {e}")

    # Відкрити бічне меню
    logging.info("Відкриття бічного меню...")
    try:
        menu_button = WebDriverWait(driver, 60).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[title='Main Menu']"))
        )
        menu_button.click()
        logging.info("Бічне меню відкрито.")
    except Exception as e:
        logging.error(f"Не вдалося відкрити бічне меню: {e}")

    # Натиснути на кнопку "Shop by department"
    logging.info("Натискаємо кнопку 'Shop by department'...")
    try:
        shop_by_department_button = WebDriverWait(driver, 60).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(@class, 'side-menu-item')][.//span[text()='Shop by department']]")
            )
        )
        shop_by_department_button.click()
        logging.info("Кнопка 'Shop by department' натиснута.")
    except Exception as e:
        logging.error(f"Не вдалося натиснути кнопку 'Shop by department': {e}")

    # Збір URL категорій. Використовується рекурсивна функція для збору всіх вкладених категорій
    logging.info("Збір URL категорій...")
    urls = []
    def collect_urls_from_menu():
        """
        Рекурсивно збирає URL категорій з бічного меню.
        Використовується для обходу вкладених категорій.
        """
        
        # Затримка для стабільності роботи
        time.sleep(0.5)
        # Лічильник для обходу категорій
        i = 0

        while True:
            # Отримуємо всі категорії в поточному бічному меню
            categories = driver.find_elements(By.CSS_SELECTOR, ".menu-list .side-menu-item")

            # Якщо в поточному бічному меню немає категорій, виходимо з циклу
            if i >= len(categories):
                break

            # Отримуємо наступну категорію
            category = categories[i]

            # Отримуємо тег категорії
            tag = category.tag_name.lower()

            if tag == "a":
                # Якщо елемент є посиланням, отримуємо його href
                url = category.get_attribute("href")
                if url:
                    full_url = "https://www.fruugo.co.uk" + url if url.startswith("/") else url
                    logging.info(f"- Знайдено URL категорії: {full_url}")
                    urls.append(full_url)
                else:
                    logging.warning("Знайдено посилання без href.")
            elif tag == "button":
                # Якщо елемент є кнопкою, клікаємо для переходу до підкатегорій
                logging.info(f"Відкриваємо підкатегорію: {category.text}")
                # Клікаємо на категорію для відкриття підкатегорій
                category.click()

                # Збираємо URL підкатегорій рекурсивно
                collect_urls_from_menu()

                # Повертаємося назад після обходу підкатегорій
                back_button = driver.find_element(By.CSS_SELECTOR, "button.back-button")
                if back_button:
                    back_button.click()
                    time.sleep(0.5)
                else:
                    logging.warning("Не знайдено кнопку 'Назад' для повернення до попереднього меню.")

            # Збільшуємо лічильник категорій
            i += 1

    try:
        collect_urls_from_menu()
    except Exception as e:
        logging.error(f"Помилка під час збору URL категорій: {e}")

    # Збереження URL категорій у файл
    with open("./data/categories.json", "w", encoding="utf-8") as f:
        json.dump(urls, f, ensure_ascii=False, indent=2)

    logging.info(f"Зібрано {len(urls)} URL категорій. Збережено у файл ./data/categories.json")
    return urls


# Запуск функції збору URL категорій
if __name__ == "__main__":
    collect_categories_urls()
