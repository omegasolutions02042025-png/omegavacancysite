import google.generativeai as genai
from .config import settings
from .promts import create_promt
from .generate_wl_resume import create_white_label_resume
from  openai import OpenAI, AsyncOpenAI
from app.database.dropdown_db import DropdownOptions
import asyncio
dropdown_options = DropdownOptions()


genai.configure(api_key=settings.gemini_api_key)

lite_model = genai.GenerativeModel("gemini-2.5-flash-lite")
flash_model = genai.GenerativeModel("gemini-2.5-flash")
flash_15_model = genai.GenerativeModel("gemini-1.5-flash")  # Для парсинга резюме в кабинет кандидата
pro_model = genai.GenerativeModel("gemini-2.5-pro")

client = AsyncOpenAI(api_key=settings.open_ai_api_key)




class GPT:
    def __init__(self):
        self.lite_model = lite_model
        self.flash_model = flash_model
        self.flash_15_model = flash_15_model  # Gemini 1.5 Flash для парсинга резюме
        self.pro_model = pro_model

    async def _generate_response(self, model: genai.GenerativeModel, prompt: str) -> str:
        config_params = {
            "temperature": 0.1,
        }

    
        generation_config = genai.types.GenerationConfig(**config_params)
        response = await model.generate_content_async(prompt, generation_config=generation_config)
        
        import json
        json_data = response.text
        try:
            if isinstance(json_data, str):
                # Удаляем маркеры блока кода если они есть
                
                if json_data.startswith('```json'):
                    json_data = json_data[7:]
                if json_data.endswith('```'):
                    json_data = json_data[:-3]
                json_data = json_data.strip()
            elif isinstance(json_data, dict):
                json_data = json_data
            else:
                return None
        except (json.JSONDecodeError, Exception) as e:
            return f"Ошибка парсинга JSON: {str(e)}"
        
        
        return json_data
    

    async def _generate_response_openai(self, prompt: str) -> str:
        response = await client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "Ты помощник по обработке резюме и вакансий."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=8000,
            
            
        )
        return response.choices[0].message.content

    async def generate_resume(self, resume_text: str) -> str:
        prompt = create_promt.resume_promt(resume_text=resume_text)
        return await self._generate_response(self.pro_model, prompt)

    async def generate_sverka(self, vacancy_text: str, resume_text: str, file_name: str) -> str:
        prompt = create_promt.sverka_promt(vacancy_text=vacancy_text, resume_text=resume_text, file_name=file_name)
        # Увеличиваем max_output_tokens для больших JSON-ответов (максимум для Gemini-2.5-flash-lite)
        #return await self._generate_response_openai(prompt)
        return await self._generate_response(self.pro_model, prompt)

    async def create_finalist_mail(self, resume_json: dict, username: str) -> str:
        prompt = create_promt.finalist_mail_promt(json_data=resume_json, username=username)
        return await self._generate_response(self.flash_model, prompt)
    
    async def create_utochnenie_mail(self, resume_json: dict, username: str, vacancy_text : str) -> str:
        prompt = create_promt.utochnenie_mail_promt(json_data=resume_json, username=username, vacancy_text=vacancy_text)
        return await self._generate_response(self.pro_model, prompt)

    async def create_otkaz_mail(self, resume_json: dict, username: str) -> str:
        prompt = create_promt.otkaz_mail_promt(json_data=resume_json, username=username)
        return await self._generate_response(self.flash_model, prompt)
    
    async def create_klient_mail(self, resume_json: dict, tg_username: str, additional_notes: str = "") -> str:
        prompt = create_promt.create_klient_mail_promt(json_data=resume_json, tg_username=tg_username, additional_notes=additional_notes)
        print("Klient mail prompt:", prompt)
        return await self._generate_response(self.lite_model, prompt)
    
    async def generate_wl_resume(self, candidate_text: str,
                                   vacancy_text: str,
                                   utochnenie=None,
                                   username = ""):
        return await create_white_label_resume(candidate_text,vacancy_text,self.pro_model,utochnenie,username)

    async def create_candidate_profile(self, text) -> str:
        
        specializations = await dropdown_options.get_specializations()
        print("Specializations:", specializations)
        
        prompt = create_promt.candidate_profile_promt(text=text, allowed_specializations=specializations)
        return await self._generate_response(self.flash_model, prompt)

    async def parse_resume_for_cabinet(self, resume_text: str) -> dict:
        """
        Парсит резюме для кабинета кандидата, используя Gemini 1.5 Flash.
        Возвращает упрощенную структуру для маппинга на CandidateProfile.
        
        Args:
            resume_text: Текст резюме
            
        Returns:
            dict: Словарь с полями: grade, stack, bio, experience_years
        """
        prompt = f"""
Ты — ИИ-парсер резюме для личного кабинета кандидата.

Извлеки из текста резюме следующие данные и верни ТОЛЬКО валидный JSON-объект без комментариев и пояснений.

Требуемая структура JSON:
{{
  "grade": string | null,              // ОДНО из: "JUNIOR", "MIDDLE", "SENIOR", "LEAD" (или null)
  "stack": array<string> | null,        // Массив технологий: ["Python", "FastAPI", "PostgreSQL"]
  "bio": string | null,                 // Краткое описание о себе (2-4 предложения)
  "experience_years": number | null     // Общий опыт работы в годах (целое число)
}}

Правила для grade:
- "junior", "jr", "младший", "джуниор" → "JUNIOR"
- "middle", "mid", "средний" → "MIDDLE"
- "senior", "sr", "сеньор", "старший" → "SENIOR"
- "lead", "team lead", "tech lead", "ведущий", "лид" → "LEAD"
- Если не указано явно — null

Правила для stack:
- Извлеки все упомянутые технологии, языки программирования, фреймворки
- Верни массив уникальных значений
- Пример: ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"]
- Если технологий нет — null

Правила для bio:
- Извлеки раздел "О себе", "About", "Summary" или краткое описание
- Если такого раздела нет, составь краткое описание на основе опыта работы (2-4 предложения)
- Если информации недостаточно — null

Правила для experience_years:
- Вычисли общий опыт работы на основе всех мест работы
- Верни целое число (например, 5 для "5 лет", 3 для "3 года")
- Если опыт не указан — null

ВАЖНО: Верни ТОЛЬКО JSON, без Markdown, без комментариев, без текста вокруг.

ТЕКСТ РЕЗЮМЕ:
{resume_text}
"""
        
        # Используем Gemini 1.5 Flash с принудительным JSON режимом
        generation_config = genai.types.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json"
        )
        
        try:
            response = await self.flash_15_model.generate_content_async(
                prompt,
                generation_config=generation_config
            )
            
            import json
            json_text = response.text.strip()
            
            # Убираем маркеры кода если есть
            if json_text.startswith('```json'):
                json_text = json_text[7:]
            if json_text.startswith('```'):
                json_text = json_text[3:]
            if json_text.endswith('```'):
                json_text = json_text[:-3]
            json_text = json_text.strip()
            
            result = json.loads(json_text)
            return result
            
        except Exception as e:
            print(f"Ошибка при парсинге резюме: {e}")
            # Возвращаем пустую структуру при ошибке
            return {
                "grade": None,
                "stack": None,
                "bio": None,
                "experience_years": None
            }

    # =========================
    # Методы стриминга для генерации писем
    # =========================
    
    async def _generate_response_stream(self, model: genai.GenerativeModel, prompt: str):
        """
        Генератор для стриминга ответа от Gemini API.
        Yields части текста по мере генерации в реальном времени.
        """
        generation_config = genai.types.GenerationConfig(temperature=0.1)
        
        import time
        start_time = time.time()
        print(f"[STREAM START] Начало стриминга...")

        try:
            # Используем асинхронный метод с stream=True
            # generate_content_async с stream=True возвращает асинхронный итератор
            response_stream = await model.generate_content_async(
                prompt,
                generation_config=generation_config,
                stream=True
            )
            
            chunk_idx = 0
            async for chunk in response_stream:
                # Извлекаем текст из чанка
                text_chunk = None
                if hasattr(chunk, 'text') and chunk.text:
                    text_chunk = chunk.text
                elif hasattr(chunk, 'candidates') and chunk.candidates:
                     for candidate in chunk.candidates:
                        if hasattr(candidate, 'content') and candidate.content:
                            if hasattr(candidate.content, 'parts'):
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        text_chunk = part.text
                                        break
                
                if text_chunk:
                    current_time = time.time()
                    elapsed = current_time - start_time
                    chunk_idx += 1
                    print(f"[STREAM CHUNK #{chunk_idx}] +{elapsed:.3f}s | Size: {len(text_chunk)} chars | Preview: {text_chunk[:30].replace(chr(10), ' ')}...")
                    
                    yield text_chunk
                    # Небольшая задержка не нужна для реального стриминга, 
                    # но можно оставить минимальную для разгрузки event loop
                    await asyncio.sleep(0)
            
            total_time = time.time() - start_time
            print(f"[STREAM END] Стриминг завершен. Всего времени: {total_time:.3f}s, чанков: {chunk_idx}")

        except Exception as e:
            print(f"Ошибка при стриминге: {e}")
            # Возвращаем ошибку как текст, чтобы она отобразилась (опционально) или просто завершаем
            # Лучше логировать, а вызывающий код обработает пустоту или прерывание
            return
    
    async def create_finalist_mail_stream(self, resume_json: dict, username: str):
        """Стриминговая генерация письма финалисту"""
        prompt = create_promt.finalist_mail_promt(json_data=resume_json, username=username)
        async for chunk in self._generate_response_stream(self.flash_model, prompt):
            yield chunk
    
    async def create_utochnenie_mail_stream(self, resume_json: dict, username: str, vacancy_text: str):
        """Стриминговая генерация уточняющего письма"""
        prompt = create_promt.utochnenie_mail_promt(json_data=resume_json, username=username, vacancy_text=vacancy_text)
        async for chunk in self._generate_response_stream(self.pro_model, prompt):
            yield chunk
    
    async def create_otkaz_mail_stream(self, resume_json: dict, username: str):
        """Стриминговая генерация письма об отказе"""
        prompt = create_promt.otkaz_mail_promt(json_data=resume_json, username=username)
        async for chunk in self._generate_response_stream(self.flash_model, prompt):
            yield chunk
    
    async def create_klient_mail_stream(self, resume_json: dict, tg_username: str, additional_notes: str = ""):
        """Стриминговая генерация письма клиенту"""
        prompt = create_promt.create_klient_mail_promt(json_data=resume_json, tg_username=tg_username, additional_notes=additional_notes)
        async for chunk in self._generate_response_stream(self.lite_model, prompt):
            yield chunk


        
        

gpt_generator = GPT()




