"""
Сервис для работы с валютами и расчета ставок кандидатов
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.exchange_rate import ExchangeRate
from app.database.database import CandidateProfileDB
from app.core.exchange_rate_parser import parse_cb_rf
from typing import Optional, Dict, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ExchangeRateService:
    """Сервис для работы с курсами валют"""
    
    @staticmethod
    async def get_active_rate(session: AsyncSession) -> Optional[ExchangeRate]:
        """Получить активный (текущий) курс валют"""
        query = select(ExchangeRate).where(
            ExchangeRate.is_active == True
        ).order_by(ExchangeRate.fetched_at.desc()).limit(1)
        
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_latest_rate(session: AsyncSession) -> Optional[ExchangeRate]:
        """Получить последний сохраненный курс (активный или нет)"""
        query = select(ExchangeRate).order_by(
            ExchangeRate.fetched_at.desc()
        ).limit(1)
        
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_rate(
        session: AsyncSession,
        usd_rate: float,
        eur_rate: float,
        byn_rate: float,
        status: str = "success",
        error_message: Optional[str] = None
    ) -> ExchangeRate:
        """Создать новую запись с курсами валют"""
        # Деактивируем все предыдущие курсы
        await session.execute(
            update(ExchangeRate).values(is_active=False)
        )
        
        # Создаем новую запись
        new_rate = ExchangeRate(
            usd_rate=usd_rate,
            eur_rate=eur_rate,
            byn_rate=byn_rate,
            is_active=True,
            last_update_status=status,
            error_message=error_message,
            fetched_at=datetime.now().isoformat()
        )
        
        session.add(new_rate)
        await session.commit()
        await session.refresh(new_rate)
        
        logger.info(f"Создан новый курс валют: USD={usd_rate}, EUR={eur_rate}, BYN={byn_rate}")
        return new_rate
    
    @staticmethod
    async def update_rates_from_parser(
        session: AsyncSession,
        rates_dict: Optional[dict]
    ) -> Optional[ExchangeRate]:
        """Обновить курсы из результата парсера"""
        if rates_dict is None:
            logger.warning("Не удалось получить курсы, используем последние сохраненные")
            
            last_rate = await ExchangeRateService.get_latest_rate(session)
            if last_rate:
                return await ExchangeRateService.create_rate(
                    session,
                    usd_rate=last_rate.usd_rate,
                    eur_rate=last_rate.eur_rate,
                    byn_rate=last_rate.byn_rate,
                    status="error",
                    error_message="Не удалось получить курсы от ЦБ РФ"
                )
            return None
        
        return await ExchangeRateService.create_rate(
            session,
            usd_rate=rates_dict['USD'],
            eur_rate=rates_dict['EUR'],
            byn_rate=rates_dict['BYN'],
            status="success"
        )


class CurrencyService:
    """Сервис для конвертации валют и расчета ставок"""
    
    @staticmethod
    def convert_to_rub(
        amount: float,
        from_currency: str,
        exchange_rate: ExchangeRate
    ) -> float:
        """Конвертировать сумму в рубли"""
        if from_currency == "RUB":
            return amount
        elif from_currency == "USD":
            return amount * exchange_rate.usd_rate
        elif from_currency == "EUR":
            return amount * exchange_rate.eur_rate
        elif from_currency == "BYN":
            return amount * exchange_rate.byn_rate
        else:
            raise ValueError(f"Неподдерживаемая валюта: {from_currency}")
    
    @staticmethod
    def convert_from_rub(
        amount_rub: float,
        to_currency: str,
        exchange_rate: ExchangeRate
    ) -> float:
        """Конвертировать сумму из рублей в другую валюту"""
        if to_currency == "RUB":
            return amount_rub
        elif to_currency == "USD":
            return amount_rub / exchange_rate.usd_rate
        elif to_currency == "EUR":
            return amount_rub / exchange_rate.eur_rate
        elif to_currency == "BYN":
            return amount_rub / exchange_rate.byn_rate
        else:
            raise ValueError(f"Неподдерживаемая валюта: {to_currency}")
    
    @staticmethod
    def calculate_all_rates(
        base_amount: float,
        base_currency: str,
        exchange_rate: ExchangeRate
    ) -> Dict[str, float]:
        """Рассчитать ставку во всех поддерживаемых валютах"""
        amount_in_rub = CurrencyService.convert_to_rub(
            base_amount, base_currency, exchange_rate
        )
        
        return {
            'RUB': round(amount_in_rub, 2),
            'USD': round(CurrencyService.convert_from_rub(amount_in_rub, 'USD', exchange_rate), 2),
            'EUR': round(CurrencyService.convert_from_rub(amount_in_rub, 'EUR', exchange_rate), 2),
            'BYN': round(CurrencyService.convert_from_rub(amount_in_rub, 'BYN', exchange_rate), 2),
        }
    
    @staticmethod
    async def update_exchange_rates(session: AsyncSession) -> Optional[ExchangeRate]:
        """Обновить курсы валют из ЦБ РФ"""
        logger.info("Начинаем обновление курсов валют...")
        
        rates = parse_cb_rf()
        new_rate = await ExchangeRateService.update_rates_from_parser(session, rates)
        
        if new_rate:
            logger.info(f"Курсы валют успешно обновлены: {new_rate.fetched_at}")
        else:
            logger.error("Не удалось обновить курсы валют")
        
        return new_rate
    
    @staticmethod
    async def get_candidate_rates_with_conversion(
        session: AsyncSession,
        base_amount: Optional[float],
        base_currency: Optional[str] = "RUB"
    ) -> Tuple[Optional[Dict[str, float]], Optional[ExchangeRate]]:
        """Получить ставки кандидата во всех валютах"""
        if base_amount is None or base_amount <= 0:
            return None, None
        
        exchange_rate = await ExchangeRateService.get_active_rate(session)
        
        if not exchange_rate:
            logger.warning("Активный курс не найден в БД")
            return None, None
        
        rates = CurrencyService.calculate_all_rates(
            base_amount, base_currency, exchange_rate
        )
        
        return rates, exchange_rate
    
    @staticmethod
    async def ensure_rates_available(session: AsyncSession) -> bool:
        """Убедиться, что курсы валют доступны в БД"""
        active_rate = await ExchangeRateService.get_active_rate(session)
        
        if not active_rate:
            logger.info("Активный курс не найден, выполняем первичное обновление...")
            new_rate = await CurrencyService.update_exchange_rates(session)
            return new_rate is not None
        
        return True


class CandidateRateService:
    """Сервис для работы со ставками кандидатов"""
    
    @staticmethod
    async def update_candidate_rate(
        session: AsyncSession,
        candidate_id: int,
        base_amount: float,
        base_currency: str = "RUB",
        rate_type: str = "monthly"
    ) -> Optional[CandidateProfileDB]:
        """Обновить ставку кандидата и пересчитать во всех валютах"""
        query = select(CandidateProfileDB).where(CandidateProfileDB.id == candidate_id)
        result = await session.execute(query)
        candidate = result.scalar_one_or_none()
        
        if not candidate:
            logger.error(f"Кандидат с ID {candidate_id} не найден")
            return None
        
        exchange_rate = await ExchangeRateService.get_active_rate(session)
        
        if not exchange_rate:
            logger.error("Активный курс не найден")
            return None
        
        rates = CurrencyService.calculate_all_rates(
            base_amount, base_currency, exchange_rate
        )
        
        candidate.base_rate_amount = base_amount
        candidate.base_rate_currency = base_currency
        candidate.rate_type = rate_type
        candidate.rate_rub = rates['RUB']
        candidate.rate_usd = rates['USD']
        candidate.rate_eur = rates['EUR']
        candidate.rate_byn = rates['BYN']
        candidate.rates_calculated_at = datetime.now().isoformat()
        candidate.exchange_rate_snapshot_id = exchange_rate.id
        candidate.salary_usd = rates['USD']
        
        await session.commit()
        await session.refresh(candidate)
        
        logger.info(f"Ставка кандидата {candidate_id} обновлена: {base_amount} {base_currency}")
        return candidate
    
    @staticmethod
    async def get_candidate_with_rates(
        session: AsyncSession,
        candidate_id: int
    ) -> Optional[CandidateProfileDB]:
        """Получить кандидата со ставками"""
        query = select(CandidateProfileDB).where(CandidateProfileDB.id == candidate_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def recalculate_candidate_rates(
        session: AsyncSession,
        candidate_id: int
    ) -> Optional[CandidateProfileDB]:
        """Пересчитать ставки кандидата с актуальным курсом"""
        candidate = await CandidateRateService.get_candidate_with_rates(session, candidate_id)
        
        if not candidate or not candidate.base_rate_amount:
            logger.warning(f"Кандидат {candidate_id} не найден или у него нет ставки")
            return None
        
        return await CandidateRateService.update_candidate_rate(
            session,
            candidate_id,
            candidate.base_rate_amount,
            candidate.base_rate_currency or "RUB",
            candidate.rate_type or "monthly"
        )
    
    @staticmethod
    async def recalculate_all_candidates_rates(
        session: AsyncSession,
        user_id: Optional[int] = None
    ) -> int:
        """Пересчитать ставки всех кандидатов с актуальным курсом"""
        exchange_rate = await ExchangeRateService.get_active_rate(session)
        
        if not exchange_rate:
            logger.error("Активный курс не найден")
            return 0
        
        query = select(CandidateProfileDB).where(
            CandidateProfileDB.base_rate_amount.isnot(None)
        )
        
        if user_id:
            query = query.where(CandidateProfileDB.user_id == user_id)
        
        result = await session.execute(query)
        candidates = result.scalars().all()
        
        updated_count = 0
        
        for candidate in candidates:
            try:
                rates = CurrencyService.calculate_all_rates(
                    candidate.base_rate_amount,
                    candidate.base_rate_currency or "RUB",
                    exchange_rate
                )
                
                candidate.rate_rub = rates['RUB']
                candidate.rate_usd = rates['USD']
                candidate.rate_eur = rates['EUR']
                candidate.rate_byn = rates['BYN']
                candidate.rates_calculated_at = datetime.now().isoformat()
                candidate.exchange_rate_snapshot_id = exchange_rate.id
                candidate.salary_usd = rates['USD']
                
                updated_count += 1
                
            except Exception as e:
                logger.error(f"Ошибка пересчета ставки для кандидата {candidate.id}: {e}")
                continue
        
        await session.commit()
        
        logger.info(f"Пересчитано ставок: {updated_count} кандидатов")
        return updated_count
