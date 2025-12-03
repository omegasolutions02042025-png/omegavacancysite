from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class ExchangeRate(SQLModel, table=True):
    """
    Таблица для хранения курсов валют от ЦБ РФ.
    Курсы хранятся относительно рубля (RUB).
    """
    __tablename__ = "exchange_rates"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Курсы валют относительно RUB
    usd_rate: Optional[float] = Field(default=None, description="Курс USD к RUB")
    eur_rate: Optional[float] = Field(default=None, description="Курс EUR к RUB")
    byn_rate: Optional[float] = Field(default=None, description="Курс BYN к RUB")
    
    # Метаданные
    fetched_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Дата и время получения курсов",
        index=True
    )
    is_active: bool = Field(
        default=True,
        description="Флаг актуального среза курса",
        index=True
    )
    
    # Информация о последнем запуске парсера
    last_update_status: Optional[str] = Field(
        default="success",
        description="Статус последнего обновления: success, error"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Сообщение об ошибке при обновлении"
    )

