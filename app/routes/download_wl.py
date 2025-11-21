from fastapi import APIRouter, HTTPException
import os
from fastapi.responses import FileResponse
import re

router = APIRouter(tags=["download"], prefix="/api/wl")



@router.get("/download/{file_path:path}")
async def download_wl(file_path: str):
    print(f"Requested download for file_path: {file_path}")
    # Поддержим старые ссылки с подкаталогами: берём только basename
    filename = os.path.basename(file_path)
    print(f"Extracted filename: {filename}")
    file_path = 'WhiteLabel_Resume/' + filename
    print(f"Full file path resolved to: {file_path}")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    # проверка имени
  