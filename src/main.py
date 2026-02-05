import os
import queue
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd
from deep_translator import GoogleTranslator
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

MAX_PAGES = 34


def translate_text(text, target_lang="ru"):
    try:
        if not text:
            return ""
        return GoogleTranslator(source="auto", target=target_lang).translate(text)
    except Exception:
        return text


def smooth_scroll(driver):
    last_height = 0
    current_height = driver.execute_script("return document.body.scrollHeight")

    while last_height != current_height:
        last_height = current_height
        for i in range(0, current_height, 200):
            driver.execute_script(f"window.scrollTo(0, {i});")
            time.sleep(0.02)
        time.sleep(0.4)
        current_height = driver.execute_script("return document.body.scrollHeight")


def scrape_items_on_page(driver, log):
    smooth_scroll(driver)
    time.sleep(0.3)

    cards = driver.find_elements(By.CSS_SELECTOR, "a[class*='i18n-card-wrap']")

    if len(cards) < 40:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        smooth_scroll(driver)
        time.sleep(0.3)
        cards = driver.find_elements(By.CSS_SELECTOR, "a[class*='i18n-card-wrap']")

    if not cards:
        return []

    log(f"  -> РќР°Р№РґРµРЅРѕ РєР°СЂС‚РѕС‡РµРє: {len(cards)}")

    items_data = []

    for card in cards:
        try:
            link = card.get_attribute("href")

            try:
                title_elem = card.find_element(By.CLASS_NAME, "offer-title")
                title_cn = title_elem.get_attribute("textContent").strip()
            except Exception:
                title_cn = card.text.split("\n")[0]

            try:
                price_elem = card.find_element(By.CLASS_NAME, "price-wrap")
                price = price_elem.text.replace("\n", "").strip()
            except Exception:
                price = "0"

            try:
                img_elem = card.find_element(By.CSS_SELECTOR, "img")
                img_src = img_elem.get_attribute("src")
                if not img_src:
                    img_src = img_elem.get_attribute("data-src")
                if not img_src:
                    img_src = img_elem.get_attribute("data-original")
            except Exception:
                img_src = ""

            try:
                moq = card.find_element(By.CLASS_NAME, "overseas-begin-quantity-wrap").text.strip()
            except Exception:
                moq = ""

            try:
                sales = card.find_element(By.CLASS_NAME, "sale-amount-wrap").text.strip()
            except Exception:
                sales = ""

            try:
                rating = card.find_element(By.CLASS_NAME, "star-level-text").text.strip()
            except Exception:
                rating = ""

            try:
                tags = card.find_elements(By.CLASS_NAME, "promotion-tags")
                promo_text = ", ".join([t.text for t in tags])
            except Exception:
                promo_text = ""

            try:
                return_rate = card.find_element(By.CLASS_NAME, "overseas-return-rate-wrap").text.strip()
            except Exception:
                return_rate = ""

            title_ru = translate_text(title_cn)

            items_data.append(
                {
                    "Title_CN": title_cn,
                    "Title_RU": title_ru,
                    "Price": price,
                    "MOQ": moq,
                    "Sales": sales,
                    "Rating": rating,
                    "Return_Rate": return_rate,
                    "Promo": promo_text,
                    "Link": link,
                    "Image": img_src,
                }
            )
        except Exception:
            continue

    return items_data


class ScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("1688_soft")
        self.root.resizable(False, False)

        self.driver = None
        self.main_categories = []
        self.subcategories = []
        self.subcategories_for_main = None
        self.running = False

        self.log_queue = queue.Queue()

        self._build_ui()
        self.root.after(100, self._process_log_queue)

    def _build_ui(self):
        colors = {
            "bg": "#f5f2ee",
            "card": "#ffffff",
            "border": "#d6cfc8",
            "text": "#2a2a2a",
            "muted": "#6a625c",
            "accent": "#2f6f6d",
            "accent_dark": "#255b59",
            "danger": "#c2413b",
            "danger_dark": "#a3342f",
            "field": "#ffffff",
        }

        self.root.configure(bg=colors["bg"])
        self.root.option_add("*Font", "Segoe UI 10")
        self.root.option_add("*Foreground", colors["text"])

        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background=colors["bg"])
        style.configure("Card.TFrame", background=colors["card"], relief="solid", borderwidth=1)
        style.configure("Header.TLabel", background=colors["bg"], foreground=colors["text"], font=("Segoe UI Semibold", 16))
        style.configure("Sub.TLabel", background=colors["bg"], foreground=colors["muted"], font=("Segoe UI", 10))
        style.configure("TLabel", background=colors["bg"], foreground=colors["text"])
        style.configure("Card.TLabel", background=colors["card"], foreground=colors["text"])
        style.configure("TLabelframe", background=colors["bg"], borderwidth=0)
        style.configure("TLabelframe.Label", background=colors["bg"], foreground=colors["muted"], font=("Segoe UI Semibold", 10))
        style.configure("TEntry", fieldbackground=colors["field"], foreground=colors["text"])
        style.configure("Primary.TButton", background=colors["accent"], foreground="white", padding=(14, 6))
        style.configure("Ghost.TButton", background=colors["card"], foreground=colors["text"], padding=(14, 6))
        style.configure("Danger.TButton", background=colors["danger"], foreground="white", padding=(10, 5))
        style.map(
            "Primary.TButton",
            background=[("active", colors["accent_dark"])],
            foreground=[("disabled", "#e8e5e1")],
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#efebe7")],
        )
        style.map(
            "Danger.TButton",
            background=[("active", colors["danger_dark"])],
        )

        main_frame = ttk.Frame(self.root, padding=16, style="App.TFrame")
        main_frame.grid(row=0, column=0, sticky="nsew")

        header = ttk.Frame(main_frame, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="1688_soft", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Парсер товаров 1688", style="Sub.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

        actions = ttk.Frame(main_frame, style="App.TFrame")
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Открыть браузер", style="Ghost.TButton", command=self.start_browser).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(actions, text="Начать парсинг", style="Primary.TButton", command=self.start_parsing).grid(
            row=0, column=1, sticky="ew"
        )

        params = ttk.LabelFrame(main_frame, text="Параметры", padding=12)
        params.grid(row=2, column=0, sticky="ew")
        params.columnconfigure(1, weight=1)

        ttk.Label(params, text="Номер главной категории:", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.main_cat_var = tk.StringVar()
        ttk.Entry(params, textvariable=self.main_cat_var, width=10).grid(row=0, column=1, sticky="w", pady=(0, 6))

        ttk.Label(params, text="Номер подкатегории:", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.sub_cat_var = tk.StringVar()
        ttk.Entry(params, textvariable=self.sub_cat_var, width=10).grid(row=1, column=1, sticky="w", pady=(0, 6))

        ttk.Label(params, text="Путь экспорта:", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.export_path_var = tk.StringVar(value=os.getcwd())
        ttk.Entry(params, textvariable=self.export_path_var, width=44).grid(row=2, column=1, sticky="ew")

        path_actions = ttk.Frame(params, style="App.TFrame")
        path_actions.grid(row=3, column=1, sticky="e", pady=(8, 0))
        ttk.Button(path_actions, text="Выбрать папку", style="Ghost.TButton", command=self.choose_export_path).grid(
            row=0, column=0, sticky="e"
        )
        ttk.Button(path_actions, text="Связь: @EcommerceGr", style="Danger.TButton", command=self.open_contact).grid(
            row=0, column=1, sticky="e", padx=(8, 0)
        )

        ttk.Separator(main_frame, orient="horizontal").grid(row=3, column=0, sticky="ew", pady=(12, 8))

        ttk.Label(main_frame, text="Логирование", style="Sub.TLabel").grid(row=4, column=0, sticky="w")
        self.log_text = tk.Text(
            main_frame,
            height=18,
            width=72,
            state="disabled",
            bg=colors["card"],
            fg=colors["text"],
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=colors["border"],
            highlightcolor=colors["border"],
        )
        self.log_text.grid(row=5, column=0, sticky="ew", pady=(6, 0))

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}")

    def _process_log_queue(self):
        while not self.log_queue.empty():
            message = self.log_queue.get_nowait()
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(100, self._process_log_queue)

    def open_contact(self):
        webbrowser.open("https://t.me/EcommerceGr")

    def choose_export_path(self):
        path = filedialog.askdirectory(initialdir=self.export_path_var.get())
        if path:
            self.export_path_var.set(path)

    def start_browser(self):
        if self.running:
            self.log("РџСЂРѕС†РµСЃСЃ СѓР¶Рµ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ.")
            return
        if self.driver:
            self.log("Р‘СЂР°СѓР·РµСЂ СѓР¶Рµ РѕС‚РєСЂС‹С‚.")
            return
        self.running = True
        threading.Thread(target=self._start_browser_worker, daemon=True).start()

    def _start_browser_worker(self):
        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            self.log("РћС‚РєСЂС‹РІР°РµРј https://alibaba.cn ...")
            self.driver.get("https://alibaba.cn")
            self.log("Р­РўРђРџ 1: Р’РҐРћР”")
            self.log("1. Р’РѕР№РґРёС‚Рµ РІ Р°РєРєР°СѓРЅС‚.")
            self.log("2. РџРѕСЃР»Рµ РІС…РѕРґР° РЅР°Р¶РјРёС‚Рµ 'РќР°С‡Р°С‚СЊ РїР°СЂСЃРёРЅРі'.")
        except Exception as exc:
            self.log(f"РћС€РёР±РєР° Р·Р°РїСѓСЃРєР° Р±СЂР°СѓР·РµСЂР°: {exc}")
            self.driver = None
        finally:
            self.running = False

    def start_parsing(self):
        if self.running:
            self.log("РџСЂРѕС†РµСЃСЃ СѓР¶Рµ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ.")
            return
        if not self.driver:
            messagebox.showwarning("1688_soft", "РЎРЅР°С‡Р°Р»Р° РѕС‚РєСЂРѕР№С‚Рµ Р±СЂР°СѓР·РµСЂ.")
            return
        self.running = True
        threading.Thread(target=self._parse_worker, daemon=True).start()

    def _parse_worker(self):
        try:
            if not self.main_categories:
                self._scan_main_categories()
                self.log("Р’РІРµРґРёС‚Рµ РЅРѕРјРµСЂ РіР»Р°РІРЅРѕР№ РєР°С‚РµРіРѕСЂРёРё Рё РЅР°Р¶РјРёС‚Рµ 'РќР°С‡Р°С‚СЊ РїР°СЂСЃРёРЅРі' РµС‰Рµ СЂР°Р·.")
                return

            main_idx = self._parse_index(self.main_cat_var.get(), len(self.main_categories), "РіР»Р°РІРЅРѕР№ РєР°С‚РµРіРѕСЂРёРё")
            if main_idx is None:
                return

            if self.subcategories_for_main != main_idx or not self.subcategories:
                self._scan_subcategories(main_idx)
                self.log("Р’РІРµРґРёС‚Рµ РЅРѕРјРµСЂ РїРѕРґРєР°С‚РµРіРѕСЂРёРё Рё РЅР°Р¶РјРёС‚Рµ 'РќР°С‡Р°С‚СЊ РїР°СЂСЃРёРЅРі' РµС‰Рµ СЂР°Р·.")
                return

            sub_idx = self._parse_index(self.sub_cat_var.get(), len(self.subcategories), "РїРѕРґРєР°С‚РµРіРѕСЂРёРё")
            if sub_idx is None:
                return

            export_dir = self.export_path_var.get().strip()
            if not export_dir:
                self.log("РЈРєР°Р¶РёС‚Рµ РїСѓС‚СЊ СЌРєСЃРїРѕСЂС‚Р°.")
                return
            if not os.path.isdir(export_dir):
                self.log("РџСѓС‚СЊ СЌРєСЃРїРѕСЂС‚Р° РЅРµ РЅР°Р№РґРµРЅ. Р’С‹Р±РµСЂРёС‚Рµ СЃСѓС‰РµСЃС‚РІСѓСЋС‰СѓСЋ РїР°РїРєСѓ.")
                return

            selected_main_cat_name = self.main_categories[main_idx]
            selected_sub = self.subcategories[sub_idx]

            safe_name = "".join([c for c in selected_sub["name"] if c.isalpha() or c.isdigit()]).rstrip()
            if not safe_name:
                safe_name = "export"
            filename = os.path.join(export_dir, f"parsed_{safe_name}.csv")

            if os.path.exists(filename):
                os.remove(filename)

            self.log(f"РџР°СЂСЃРёРЅРі: {selected_sub['name']}")
            self.log(f"Р”Р°РЅРЅС‹Рµ Р±СѓРґСѓС‚ СЃРѕС…СЂР°РЅСЏС‚СЊСЃСЏ РІ: {filename} (РїРѕСЃР»Рµ РєР°Р¶РґРѕР№ СЃС‚СЂР°РЅРёС†С‹)")

            self.driver.get(selected_sub["url"])
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[class*='i18n-card-wrap']"))
                )
            except Exception:
                time.sleep(1)

            page_num = 1
            total_items_collected = 0

            cols = [
                "Main_Category",
                "Sub_Group",
                "Sub_Category",
                "Title_CN",
                "Title_RU",
                "Price",
                "MOQ",
                "Sales",
                "Rating",
                "Return_Rate",
                "Promo",
                "Link",
                "Image",
            ]

            while page_num <= MAX_PAGES:
                self.log(f"--- РЎС‚СЂР°РЅРёС†Р° {page_num} ---")

                items = scrape_items_on_page(self.driver, self.log)

                if len(items) == 0:
                    self.log("!!! РџРЈРЎРўРћ. Р’РѕР·РјРѕР¶РЅРѕ РљРђРџР§Рђ !!!")
                    messagebox.showinfo("1688_soft", "РџСЂРѕР№РґРёС‚Рµ РєР°РїС‡Сѓ РІ Р±СЂР°СѓР·РµСЂРµ Рё РЅР°Р¶РјРёС‚Рµ OK.")
                    items = scrape_items_on_page(self.driver, self.log)
                    if len(items) == 0:
                        break

                for item in items:
                    item["Main_Category"] = selected_main_cat_name
                    item["Sub_Group"] = selected_sub["group"]
                    item["Sub_Category"] = selected_sub["name"]

                if items:
                    df = pd.DataFrame(items)
                    df = df.reindex(columns=cols)

                    header_mode = not os.path.exists(filename)
                    df.to_csv(filename, mode="a", index=False, header=header_mode, encoding="utf-8-sig", sep=";")

                    total_items_collected += len(items)
                    self.log(f"РЎРѕР±СЂР°РЅРѕ {len(items)} (Р’СЃРµРіРѕ: {total_items_collected}). РЎРѕС…СЂР°РЅРµРЅРѕ РІ С„Р°Р№Р».")

                try:
                    next_btns = self.driver.find_elements(By.CSS_SELECTOR, ".fui-arrow.fui-next")
                    if not next_btns:
                        break

                    btn = next_btns[0]
                    if "disabled" in btn.get_attribute("class") or "fui-prev-disabled" in btn.get_attribute("class"):
                        self.log("Р­С‚Рѕ РїРѕСЃР»РµРґРЅСЏСЏ СЃС‚СЂР°РЅРёС†Р°.")
                        break

                    self.driver.execute_script("arguments[0].click();", btn)
                    page_num += 1

                    try:
                        WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "a[class*='i18n-card-wrap']"))
                        )
                    except Exception:
                        time.sleep(0.5)
                except Exception:
                    break

            self.log(f"Р“РћРўРћР’Рћ! Р’РµСЃСЊ РїСЂРѕС†РµСЃСЃ Р·Р°РІРµСЂС€РµРЅ. Р¤Р°Р№Р»: {filename}")
        except Exception as exc:
            self.log(f"РџСЂРѕРёР·РѕС€Р»Р° РѕС€РёР±РєР°: {exc}")
            self.log("РќРµ РІРѕР»РЅСѓР№С‚РµСЃСЊ, РІСЃС‘ С‡С‚Рѕ СѓСЃРїРµР»Рё СЃРѕР±СЂР°С‚СЊ РґРѕ СЌС‚РѕРіРѕ РјРѕРјРµРЅС‚Р° - СѓР¶Рµ РІ С„Р°Р№Р»Рµ CSV.")
        finally:
            self.log("Р Р°Р±РѕС‚Р° Р·Р°РІРµСЂС€РµРЅР°.")
            self.running = False

    def _parse_index(self, value, max_len, label):
        try:
            idx = int(value) - 1
        except ValueError:
            self.log(f"Р’РІРµРґРёС‚Рµ РєРѕСЂСЂРµРєС‚РЅС‹Р№ РЅРѕРјРµСЂ РґР»СЏ {label}.")
            return None
        if idx < 0 or idx >= max_len:
            self.log(f"РќРѕРјРµСЂ {label} РІРЅРµ РґРёР°РїР°Р·РѕРЅР° (1-{max_len}).")
            return None
        return idx

    def _scan_main_categories(self):
        self.log("РЎРєР°РЅРёСЂСѓРµРј РєР°С‚РµРіРѕСЂРёРё...")
        main_cat_elems = self.driver.find_elements(By.CSS_SELECTOR, "li.lv1Item--O30i9KsN")
        if not main_cat_elems:
            self.log("РљР°С‚РµРіРѕСЂРёРё РЅРµ РЅР°Р№РґРµРЅС‹. РЈР±РµРґРёС‚РµСЃСЊ, С‡С‚Рѕ РІС‹ РІРѕС€Р»Рё Рё СЃС‚СЂР°РЅРёС†Р° Р·Р°РіСЂСѓР·РёР»Р°СЃСЊ.")
            return

        main_cats_list = []
        for i, el in enumerate(main_cat_elems):
            try:
                links = el.find_elements(By.TAG_NAME, "a")
                clean_texts = [
                    l.get_attribute("textContent").strip()
                    for l in links
                    if l.get_attribute("textContent").strip() and "f-14" in l.get_attribute("class")
                ]
                if not clean_texts:
                    clean_texts = [
                        l.get_attribute("textContent").strip() for l in links if l.get_attribute("textContent").strip()
                    ][:3]
                name = " / ".join(clean_texts)
                main_cats_list.append(name)
                self.log(f"{i + 1}. {name}")
            except Exception:
                main_cats_list.append("Unknown")

        self.main_categories = main_cats_list

    def _scan_subcategories(self, main_idx):
        self.log("РџРѕР»СѓС‡Р°РµРј РїРѕРґРєР°С‚РµРіРѕСЂРёРё...")
        main_cat_elems = self.driver.find_elements(By.CSS_SELECTOR, "li.lv1Item--O30i9KsN")
        if main_idx >= len(main_cat_elems):
            self.log("Р“Р»Р°РІРЅР°СЏ РєР°С‚РµРіРѕСЂРёСЏ РЅРµ РЅР°Р№РґРµРЅР°. РћР±РЅРѕРІРёС‚Рµ СЃС‚СЂР°РЅРёС†Сѓ Рё РїРѕРїСЂРѕР±СѓР№С‚Рµ СЃРЅРѕРІР°.")
            return

        target_li = main_cat_elems[main_idx]
        self.driver.execute_script(
            "var ev = document.createEvent('MouseEvents'); ev.initEvent('mouseenter', true, false); arguments[0].dispatchEvent(ev);",
            target_li,
        )
        time.sleep(1.5)

        try:
            popup_ul = WebDriverWait(target_li, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "cate_content--TUOLAWjz"))
            )
            sub_rows = popup_ul.find_elements(By.TAG_NAME, "li")
        except Exception:
            self.log("РџРѕРґРєР°С‚РµРіРѕСЂРёРё РЅРµ РЅР°Р№РґРµРЅС‹. РџРѕРїСЂРѕР±СѓР№С‚Рµ РµС‰Рµ СЂР°Р·.")
            return

        available_subcats = []
        count = 1
        for row in sub_rows:
            try:
                group_name = row.find_element(By.CLASS_NAME, "cTitle--Md3f91iK").get_attribute("textContent").strip()
            except Exception:
                group_name = "РћР±С‰РµРµ"

            try:
                box = row.find_element(By.CLASS_NAME, "cBox--sueyS7qB")
                links = box.find_elements(By.TAG_NAME, "a")
                for link in links:
                    item_name = link.get_attribute("textContent").strip()
                    item_url = link.get_attribute("href")
                    if item_name and item_url:
                        available_subcats.append({"group": group_name, "name": item_name, "url": item_url})
                        self.log(f"{count}. [{group_name}] {item_name}")
                        count += 1
            except Exception:
                continue

        self.subcategories = available_subcats
        self.subcategories_for_main = main_idx


def main():
    root = tk.Tk()
    app = ScraperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()


