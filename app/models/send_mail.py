from pydantic import BaseModel


class SendMail(BaseModel):
    vacancy_id: str
    candidate_fullname : str
    contact : str
    message : str
    
class TelegramNotifyIn(BaseModel):
    user_id: int
    vacancy_id: str
    candidate_fullname: str


class NotificationOut(BaseModel):
    id: int
    type: str = "telegram_message"
    vacancy_id: str
    candidate_fullname: str
    message: str