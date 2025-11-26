import google.generativeai as genai
from .config import settings
from .promts import create_promt
from .generate_wl_resume import create_white_label_resume
from  openai import OpenAI, AsyncOpenAI
from app.database.dropdown_db import DropdownOptions
dropdown_options = DropdownOptions()


genai.configure(api_key=settings.gemini_api_key)

lite_model = genai.GenerativeModel("gemini-2.5-flash-lite")
flash_model = genai.GenerativeModel("gemini-2.5-flash")
pro_model = genai.GenerativeModel("gemini-2.5-pro")

client = AsyncOpenAI(api_key=settings.open_ai_api_key)




class GPT:
    def __init__(self):
        self.lite_model = lite_model
        self.flash_model = flash_model
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
        return await self._generate_response(self.flash_model, prompt)

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


        
        

gpt_generator = GPT()




