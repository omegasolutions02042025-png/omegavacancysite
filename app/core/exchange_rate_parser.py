"""
Сервис для получения курсов валют от ЦБ РФ
"""
import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


def parse_cb_rf() -> Optional[Dict[str, float]]:
    """
    Парсит курсы валют с сайта ЦБ РФ.
    
    Returns:
        Dict с курсами USD, EUR, BYN относительно рубля или None при ошибке
    """
    try:
        url = 'https://www.cbr.ru/currency_base/daily/'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.banki.ru/products/currency/cb/",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'class': 'data'})
        
        if not table:
            logger.error("Таблица с курсами не найдена на странице ЦБ РФ")
            return None
            
        rows = table.find_all('tr')
        
        if len(rows) < 20:
            logger.error(f"Недостаточно строк в таблице: {len(rows)}")
            return None
        
        # Парсим курсы из таблицы
        # Индексы могут меняться, поэтому лучше искать по коду валюты
        rates = {}
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 5:
                # Структура: Цифр. код | Букв. код | Единиц | Валюта | Курс
                currency_code = cells[1].text.strip()
                units = cells[2].text.strip()
                rate_text = cells[4].text.replace(" ", "").replace(",", ".").strip()
                
                try:
                    rate = float(rate_text)
                    units_count = int(units)
                    
                    # Нормализуем курс к 1 единице валюты
                    normalized_rate = rate / units_count
                    
                    if currency_code == "USD":
                        rates['USD'] = normalized_rate
                    elif currency_code == "EUR":
                        rates['EUR'] = normalized_rate
                    elif currency_code == "BYN":
                        rates['BYN'] = normalized_rate
                        
                except (ValueError, ZeroDivisionError) as e:
                    logger.warning(f"Ошибка парсинга курса для {currency_code}: {e}")
                    continue
        
        # Проверяем, что получили все нужные валюты
        required_currencies = {'USD', 'EUR', 'BYN'}
        if not required_currencies.issubset(rates.keys()):
            missing = required_currencies - rates.keys()
            logger.error(f"Не удалось получить курсы для валют: {missing}")
            return None
        
        logger.info(f"Успешно получены курсы: {rates}")
        return rates
        
    except requests.RequestException as e:
        logger.error(f"Ошибка при запросе к ЦБ РФ: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при парсинге курсов ЦБ РФ: {e}")
        return None

