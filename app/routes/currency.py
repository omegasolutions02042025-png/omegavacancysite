"""
API роуты для работы с валютами и ставками кандидатов
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db, SessionDep
from app.services.currency_service import CurrencyService, ExchangeRateService, CandidateRateService
from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime

router = APIRouter(prefix="/api/currency", tags=["currency"])


class ExchangeRateResponse(BaseModel):
    """Ответ с курсами валют"""
    id: int
    usd_rate: float
    eur_rate: float
    byn_rate: float
    fetched_at: str
    is_active: bool
    last_update_status: str
    error_message: Optional[str] = None


class CandidateRateRequest(BaseModel):
    """Запрос на обновление ставки кандидата"""
    base_amount: float = Field(gt=0, description="Основная ставка (должна быть положительной)")
    base_currency: str = Field(default="RUB", description="Валюта основной ставки")
    rate_type: str = Field(default="monthly", description="Тип ставки: hourly, monthly, yearly")


class CandidateRateResponse(BaseModel):
    """Ответ со ставками кандидата во всех валютах"""
    base_amount: float
    base_currency: str
    rate_type: str
    is_base: bool = Field(description="Флаг основной валюты")
    
    # Ставки во всех валютах
    rate_rub: float
    rate_usd: float
    rate_eur: float
    rate_byn: float
    
    # Метаданные
    rates_calculated_at: str
    exchange_rate_snapshot_id: int
    exchange_rate_fetched_at: str


class ConvertCurrencyRequest(BaseModel):
    """Запрос на конвертацию валюты"""
    amount: float = Field(gt=0, description="Сумма для конвертации")
    from_currency: str = Field(description="Исходная валюта (RUB, USD, EUR, BYN)")
    to_currency: str = Field(description="Целевая валюта (RUB, USD, EUR, BYN)")


class ConvertCurrencyResponse(BaseModel):
    """Ответ с результатом конвертации"""
    original_amount: float
    from_currency: str
    converted_amount: float
    to_currency: str
    exchange_rate_used: float
    calculated_at: str


@router.get("/rates/current", response_model=ExchangeRateResponse)
async def get_current_rates(session: SessionDep):
    """
    Получить текущие активные курсы валют
    """
    rate = await ExchangeRateService.get_active_rate(session)
    
    if not rate:
        raise HTTPException(
            status_code=404,
            detail="Курсы валют не найдены. Попробуйте обновить курсы."
        )
    
    return ExchangeRateResponse(
        id=rate.id,
        usd_rate=rate.usd_rate,
        eur_rate=rate.eur_rate,
        byn_rate=rate.byn_rate,
        fetched_at=rate.fetched_at,
        is_active=rate.is_active,
        last_update_status=rate.last_update_status,
        error_message=rate.error_message
    )


@router.post("/rates/refresh", response_model=ExchangeRateResponse)
async def refresh_rates(session: SessionDep):
    """
    Принудительно обновить курсы валют из ЦБ РФ
    (Админ/сервисный эндпоинт)
    """
    new_rate = await CurrencyService.update_exchange_rates(session)
    
    if not new_rate:
        raise HTTPException(
            status_code=500,
            detail="Не удалось обновить курсы валют"
        )
    
    return ExchangeRateResponse(
        id=new_rate.id,
        usd_rate=new_rate.usd_rate,
        eur_rate=new_rate.eur_rate,
        byn_rate=new_rate.byn_rate,
        fetched_at=new_rate.fetched_at,
        is_active=new_rate.is_active,
        last_update_status=new_rate.last_update_status,
        error_message=new_rate.error_message
    )


@router.post("/convert", response_model=ConvertCurrencyResponse)
async def convert_currency(
    request: ConvertCurrencyRequest,
    session: SessionDep
):
    """
    Конвертировать сумму из одной валюты в другую
    """
    # Получаем активный курс
    exchange_rate = await ExchangeRateService.get_active_rate(session)
    
    if not exchange_rate:
        raise HTTPException(
            status_code=404,
            detail="Курсы валют не найдены"
        )
    
    # Валидация валют
    supported_currencies = {'RUB', 'USD', 'EUR', 'BYN'}
    if request.from_currency not in supported_currencies:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемая исходная валюта: {request.from_currency}"
        )
    if request.to_currency not in supported_currencies:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемая целевая валюта: {request.to_currency}"
        )
    
    # Конвертируем через рубли
    amount_in_rub = CurrencyService.convert_to_rub(
        request.amount, request.from_currency, exchange_rate
    )
    converted_amount = CurrencyService.convert_from_rub(
        amount_in_rub, request.to_currency, exchange_rate
    )
    
    # Вычисляем курс конвертации
    exchange_rate_used = converted_amount / request.amount if request.amount > 0 else 0
    
    return ConvertCurrencyResponse(
        original_amount=request.amount,
        from_currency=request.from_currency,
        converted_amount=round(converted_amount, 2),
        to_currency=request.to_currency,
        exchange_rate_used=round(exchange_rate_used, 4),
        calculated_at=datetime.now().isoformat()
    )


@router.post("/calculate-rates", response_model=CandidateRateResponse)
async def calculate_candidate_rates(
    request: CandidateRateRequest,
    session: SessionDep
):
    """
    Рассчитать ставку кандидата во всех валютах
    """
    # Валидация валюты
    supported_currencies = {'RUB', 'USD', 'EUR', 'BYN'}
    if request.base_currency not in supported_currencies:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемая валюта: {request.base_currency}"
        )
    
    # Получаем ставки во всех валютах
    rates, exchange_rate = await CurrencyService.get_candidate_rates_with_conversion(
        session, request.base_amount, request.base_currency
    )
    
    if not rates or not exchange_rate:
        raise HTTPException(
            status_code=404,
            detail="Не удалось рассчитать ставки. Курсы валют не найдены."
        )
    
    return CandidateRateResponse(
        base_amount=request.base_amount,
        base_currency=request.base_currency,
        rate_type=request.rate_type,
        is_base=True,
        rate_rub=rates['RUB'],
        rate_usd=rates['USD'],
        rate_eur=rates['EUR'],
        rate_byn=rates['BYN'],
        rates_calculated_at=datetime.now().isoformat(),
        exchange_rate_snapshot_id=exchange_rate.id,
        exchange_rate_fetched_at=exchange_rate.fetched_at
    )


@router.get("/candidates/{candidate_id}/rate", response_model=CandidateRateResponse)
async def get_candidate_rate(
    candidate_id: int,
    session: SessionDep
):
    """
    Получить ставку кандидата во всех валютах
    """
    candidate = await CandidateRateService.get_candidate_with_rates(session, candidate_id)
    
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail=f"Кандидат с ID {candidate_id} не найден"
        )
    
    if not candidate.base_rate_amount:
        raise HTTPException(
            status_code=404,
            detail="У кандидата не указана ставка"
        )
    
    return CandidateRateResponse(
        base_amount=candidate.base_rate_amount,
        base_currency=candidate.base_rate_currency or "RUB",
        rate_type=candidate.rate_type or "monthly",
        is_base=True,
        rate_rub=candidate.rate_rub or 0,
        rate_usd=candidate.rate_usd or 0,
        rate_eur=candidate.rate_eur or 0,
        rate_byn=candidate.rate_byn or 0,
        rates_calculated_at=candidate.rates_calculated_at or "",
        exchange_rate_snapshot_id=candidate.exchange_rate_snapshot_id or 0,
        exchange_rate_fetched_at=""
    )


@router.put("/candidates/{candidate_id}/rate", response_model=CandidateRateResponse)
async def update_candidate_rate(
    candidate_id: int,
    request: CandidateRateRequest,
    session: SessionDep
):
    """
    Обновить ставку кандидата
    """
    # Валидация валюты
    supported_currencies = {'RUB', 'USD', 'EUR', 'BYN'}
    if request.base_currency not in supported_currencies:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемая валюта: {request.base_currency}"
        )
    
    # Обновляем ставку
    candidate = await CandidateRateService.update_candidate_rate(
        session,
        candidate_id,
        request.base_amount,
        request.base_currency,
        request.rate_type
    )
    
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail=f"Не удалось обновить ставку кандидата {candidate_id}"
        )
    
    
    return CandidateRateResponse(
        base_amount=candidate.base_rate_amount,
        base_currency=candidate.base_rate_currency,
        rate_type=candidate.rate_type,
        is_base=True,
        rate_rub=candidate.rate_rub,
        rate_usd=candidate.rate_usd,
        rate_eur=candidate.rate_eur,
        rate_byn=candidate.rate_byn,
        rates_calculated_at=candidate.rates_calculated_at,
        exchange_rate_snapshot_id=candidate.exchange_rate_snapshot_id,
        exchange_rate_fetched_at=""
    )


@router.post("/candidates/{candidate_id}/rate/recalculate", response_model=CandidateRateResponse)
async def recalculate_candidate_rate(
    candidate_id: int,
    session: SessionDep
):
    """
    Пересчитать ставку кандидата с актуальным курсом
    """
    candidate = await CandidateRateService.recalculate_candidate_rates(session, candidate_id)
    
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail=f"Не удалось пересчитать ставку кандидата {candidate_id}"
        )
    
    return CandidateRateResponse(
        base_amount=candidate.base_rate_amount,
        base_currency=candidate.base_rate_currency,
        rate_type=candidate.rate_type,
        is_base=True,
        rate_rub=candidate.rate_rub,
        rate_usd=candidate.rate_usd,
        rate_eur=candidate.rate_eur,
        rate_byn=candidate.rate_byn,
        rates_calculated_at=candidate.rates_calculated_at,
        exchange_rate_snapshot_id=candidate.exchange_rate_snapshot_id,
        exchange_rate_fetched_at=""
    )


@router.post("/candidates/recalculate-all")
async def recalculate_all_candidates_rates(
    session: SessionDep,
    user_id: Optional[int] = None
):
    """
    Пересчитать ставки всех кандидатов с актуальным курсом
    (Админ эндпоинт)
    """
    updated_count = await CandidateRateService.recalculate_all_candidates_rates(
        session, user_id
    )
    
    return {
        "message": f"Пересчитано ставок для {updated_count} кандидатов",
        "updated_count": updated_count,
        "user_id": user_id
    }

