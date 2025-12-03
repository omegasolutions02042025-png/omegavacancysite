"""
Скрипт для генерации и добавления 300000 примерных вакансий через POST запрос к /vacancy_create
"""
import asyncio
import aiohttp
import random
import json
from typing import List, Dict

# Конфигурация
BASE_URL = "http://localhost:8000"  # Измените на ваш URL если нужно
ENDPOINT = "/vacancy_create"
BATCH_SIZE = 100  # Количество вакансий в одном запросе
TOTAL_VACANCIES = 300000
CONCURRENT_REQUESTS = 10  # Количество параллельных запросов

# Данные для генерации
WORK_FORMATS = ["Удалённо", "Офис", "Гибрид", "Удалённо/Офис"]
EMPLOYMENT_TYPES = ["Full-time", "Part-time", "Contract", "Freelance"]
ENGLISH_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2", "UNSPECIFIED"]
GRADES = ["Junior", "Middle", "Senior", "Lead", "Junior/Middle", "Middle/Senior"]
COMPANY_TYPES = ["Стартап", "Продуктовая компания", "Аутсорс", "Аутстафф", "Корпорация"]
SPECIALIZATIONS = [
    "Backend_dev", "Frontend_dev", "Full-stack_dev", "Mobile_dev", 
    "DevOps", "Data Engineer", "Data Scientist", "ML Engineer",
    "QA", "QA Automation", "Security", "Game Dev", "Embedded"
]
SKILLS = [
    "Python", "JavaScript", "TypeScript", "Java", "C++", "Go", "Rust",
    "React", "Vue", "Angular", "Node.js", "FastAPI", "Django", "Flask",
    "PostgreSQL", "MongoDB", "Redis", "Kubernetes", "Docker", "AWS",
    "TensorFlow", "PyTorch", "Pandas", "NumPy", "Git", "Linux"
]
DOMAINS = [
    "FinTech", "GameDev", "E-commerce", "Healthcare", "EdTech",
    "Media", "Social Networks", "IoT", "Blockchain", "AI/ML"
]
LOCATIONS = ["РФ", "РБ", "РФ, РБ", "Европа", "США", "Удалённо", "МСК", "СПБ"]
MANAGERS = ["manager1", "manager2", "manager3", "manager4", "manager5"]
CUSTOMERS = ["Customer A", "Customer B", "Customer C", "Customer D", "Customer E"]

TITLES = [
    "Python разработчик", "JavaScript разработчик", "Full-stack разработчик",
    "Backend разработчик", "Frontend разработчик", "DevOps инженер",
    "Data Engineer", "ML Engineer", "QA Engineer", "Mobile разработчик",
    "Game Developer", "Security Engineer", "Embedded разработчик"
]

VACANCY_TEXTS = [
    "Ищем опытного разработчика для работы над интересными проектами.",
    "Требуется специалист с опытом работы в команде.",
    "Вакансия для разработчика с хорошими навыками программирования.",
    "Ищем талантливого разработчика для создания современных решений.",
    "Требуется разработчик для работы над масштабными проектами.",
    "Вакансия для специалиста с опытом в разработке программного обеспечения.",
    "Ищем разработчика для работы в дружной команде профессионалов.",
    "Требуется специалист с глубокими знаниями в области разработки.",
]


def generate_vacancy(index: int) -> Dict:
    """Генерирует одну примерную вакансию"""
    vacancy_id = f"VAC-{index:06d}"
    title = random.choice(TITLES)
    grade = random.choice(GRADES)
    
    # Генерируем списки навыков и специализаций
    num_specs = random.randint(1, 3)
    num_skills = random.randint(3, 8)
    num_domains = random.randint(1, 2)
    
    specializations = ", ".join(random.sample(SPECIALIZATIONS, num_specs))
    skills = ", ".join(random.sample(SKILLS, num_skills))
    domains = ", ".join(random.sample(DOMAINS, num_domains))
    
    return {
        "vacancy_id": vacancy_id,
        "title": f"{title} ({grade})",
        "vacancy_text": random.choice(VACANCY_TEXTS),
        "work_format": random.choice(WORK_FORMATS),
        "employment_type": random.choice(EMPLOYMENT_TYPES),
        "english_level": random.choice(ENGLISH_LEVELS),
        "grade": grade,
        "company_type": random.choice(COMPANY_TYPES),
        "specializations": specializations,
        "skills": skills,
        "domains": domains,
        "location": random.choice(LOCATIONS),
        "manager_username": random.choice(MANAGERS),
        "customer": random.choice(CUSTOMERS),
    }


def generate_batch(start_index: int, batch_size: int) -> List[Dict]:
    """Генерирует батч вакансий"""
    return [generate_vacancy(start_index + i) for i in range(batch_size)]


async def send_batch(session: aiohttp.ClientSession, batch: List[Dict], batch_num: int) -> bool:
    """Отправляет один батч вакансий"""
    try:
        async with session.post(
            f"{BASE_URL}{ENDPOINT}",
            json=batch,
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=300)
        ) as response:
            if response.status == 200:
                result = await response.json()
                print(f"✓ Батч {batch_num}: {len(batch)} вакансий добавлено успешно")
                return True
            else:
                text = await response.text()
                print(f"✗ Батч {batch_num}: Ошибка {response.status} - {text[:200]}")
                return False
    except Exception as e:
        print(f"✗ Батч {batch_num}: Исключение - {str(e)}")
        return False


async def main():
    """Основная функция"""
    print(f"🚀 Начинаем генерацию {TOTAL_VACANCIES} вакансий...")
    print(f"📦 Размер батча: {BATCH_SIZE}")
    print(f"⚡ Параллельных запросов: {CONCURRENT_REQUESTS}")
    print(f"🌐 URL: {BASE_URL}{ENDPOINT}\n")
    
    total_batches = (TOTAL_VACANCIES + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"📊 Всего батчей: {total_batches}\n")
    
    connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS)
    timeout = aiohttp.ClientTimeout(total=600)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
        
        async def send_with_semaphore(batch: List[Dict], batch_num: int):
            async with semaphore:
                return await send_batch(session, batch, batch_num)
        
        tasks = []
        successful = 0
        failed = 0
        
        for batch_num in range(total_batches):
            start_index = batch_num * BATCH_SIZE
            batch_size = min(BATCH_SIZE, TOTAL_VACANCIES - start_index)
            
            if batch_size <= 0:
                break
            
            batch = generate_batch(start_index, batch_size)
            task = send_with_semaphore(batch, batch_num + 1)
            tasks.append(task)
            
            # Отправляем батчи порциями для контроля памяти
            if len(tasks) >= CONCURRENT_REQUESTS * 2:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if result is True:
                        successful += 1
                    else:
                        failed += 1
                tasks = []
                print(f"📈 Прогресс: успешно {successful}, ошибок {failed}\n")
        
        # Отправляем оставшиеся задачи
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if result is True:
                    successful += 1
                else:
                    failed += 1
        
        print("\n" + "="*60)
        print(f"✅ Завершено!")
        print(f"✓ Успешно: {successful} батчей")
        print(f"✗ Ошибок: {failed} батчей")
        print(f"📊 Всего вакансий отправлено: ~{successful * BATCH_SIZE}")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

