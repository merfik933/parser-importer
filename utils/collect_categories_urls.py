"""
Скрипт для автоматизованого збору URL категорій з сайту https://www.fruugo.co.uk/ за допомогою Selenium та undetected_chromedriver.
Основні етапи роботи:
- Відкриває головну сторінку магазину Fruugo.
- Закриває попередження про куки (якщо воно з'являється).
- Відкриває головне бічне меню та переходить до розділу "Shop by department".
- Рекурсивно обходить всі вкладені категорії, збираючи їх URL.
- Зберігає зібрані посилання у файл ./settings/categories.json у форматі JSON.

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

def collect_categories_urls():
    # Ініціалізація браузера
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")

    driver = uc.Chrome(options=options)
    driver.get("https://www.fruugo.co.uk/")

    # Очікування завантаження сторінки та закриття попередження про куки
    try:
        decline_cookies_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[aria-label='Cookie consent'] .button.button-orange"))
        )
        decline_cookies_button.click()
    except Exception as e:
        print(f"Не вдалося закрити попередження про куки: {e}")

    # Відкрити бічне меню
    try:
        menu_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[title='Main Menu']"))
        )
        menu_button.click()
    except Exception as e:
        print(f"Не вдалося відкрити бічне меню: {e}")

    # Натиснути на кнопку "Shop by department"
    try:
        shop_by_department_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(@class, 'side-menu-item')][.//span[text()='Shop by department']]")
            )
        )
        shop_by_department_button.click()
    except Exception as e:
        print(f"Не вдалося натиснути кнопку 'Shop by department': {e}")

    # Збір URL категорій. Використовується рекурсивна функція для збору всіх вкладених категорій
    urls = []
    def collect_urls_from_menu():
        time.sleep(0.5)
        try:
            # Знаходимо всі елементи категорій у меню
            categories = driver.find_elements(By.CSS_SELECTOR, ".menu-list .side-menu-item")
        except Exception:
            return

        for i in range(len(categories)):
            try:
                # Оновлюємо список категорій, оскільки DOM міг змінитися
                categories = driver.find_elements(By.CSS_SELECTOR, ".menu-list .side-menu-item")
                if i >= len(categories):
                    break
                category = categories[i]
                tag = category.tag_name.lower()

                if tag == "a":
                    # Якщо елемент є посиланням, отримуємо його href
                    url = category.get_attribute("href")
                    if url:
                        full_url = "https://www.fruugo.co.uk" + url if url.startswith("/") else url
                        print(f"Знайдено URL категорії: {full_url}")
                        urls.append(full_url)

                elif tag == "button":
                    try:
                        # Якщо елемент є кнопкою, клікаємо для переходу до підкатегорій
                        category.click()
                        time.sleep(0.5)
                        collect_urls_from_menu()
                        # Повертаємося назад після обходу підкатегорій
                        back_button = driver.find_element(By.CSS_SELECTOR, "button.back-button")
                        if back_button:
                            back_button.click()
                            time.sleep(0.5)
                    except Exception:
                        continue
            except Exception:
                continue

    collect_urls_from_menu()

    # Збереження URL категорій у файл
    with open("./data/categories.json", "w", encoding="utf-8") as f:
        json.dump(urls, f, ensure_ascii=False, indent=2)

    print(f"Зібрано {len(urls)} URL категорій.")
    return urls


# Запуск функції збору URL категорій
if __name__ == "__main__":
    collect_categories_urls()
