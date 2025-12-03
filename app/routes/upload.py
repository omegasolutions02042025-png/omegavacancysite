import asyncio
import uuid
from pathlib import Path
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.core.config import settings
from app.core.utils import process_pdf
from app.core.gpt import gpt_generator
from app.core.utils import save_files

router = APIRouter(tags=["upload"])
# Use absolute path to templates directory
templates_dir = str(Path(__file__).resolve().parent.parent / "templates")
templates = Jinja2Templates(directory=templates_dir)

TASKS = {}  # task_id -> {status, data}
TYPES = ['pdf', 'docx', 'txt']


async def process_resume_task(resume_text: str, task_id: str):
    
    data = await gpt_generator.generate_resume(resume_text)
    TASKS[task_id] = {"status": "completed", "data": data}
    


@router.get("/upload", response_class=HTMLResponse)
async def upload_file_get(request: Request):
    return templates.TemplateResponse("upload/upload_start.html", {"request": request})


@router.post("/upload", response_class=HTMLResponse)
async def upload_file(
    request: Request,
    comment: str = Form(""),
    file: UploadFile = File(...),
):
    if file.filename.split(".")[-1] not in TYPES:
        return templates.TemplateResponse(
            'upload/upload_start.html',
            {"request" : request, "error": "Формат файла не поддерживается. Разрешены: PDF, DOCX, TXT.",},
            status_code= 400
        )
    file_path = await save_files(file)
    resume_text = process_pdf(file_path)  # если это sync-функция — ок

    task_id = str(uuid.uuid4())
    TASKS[task_id] = {"status": "processing"}

    # ВАЖНО: запускаем async-функцию фоном сами
    asyncio.create_task(process_resume_task(resume_text, task_id))

    return templates.TemplateResponse(
        "upload/wait_gemini.html",
        {"request": request, "task_id": task_id, "status": "processing"},
    )


@router.get("/status/{task_id}")
async def upload_status(task_id: str):
    """API endpoint для проверки статуса задачи"""
    if task_id not in TASKS:
        return {"status": "not_found"}
    
    task = TASKS[task_id]
    return {"status": task["status"]}

@router.get("/result/{task_id}", response_class=HTMLResponse)
async def get_result(request: Request, task_id: str):
    task = TASKS.get(task_id)
    if not task:
        return HTMLResponse("Задача не найдена", status_code=404)
    
    if task["status"] == "processing":
        return templates.TemplateResponse(
            "upload/wait_gemini.html",
            {"request": request, "task_id": task_id, "status": task["status"]},
        )
    
    return templates.TemplateResponse(
        "upload/upload_gpt_res.html",
        {"request": request, "ai_text": task["data"], "status": "completed"},
    )
