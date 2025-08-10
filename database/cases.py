"""
Case management module for Telegram Casino API

This module provides CaseManager class for:
- Case CRUD operations
- Present management
- Case-present relationships
- Initial data seeding
"""

import random
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from .models import Case, Present, CasePresent
from .manager import DatabaseManager


@dataclass
class PresentData:
    id: Optional[int]
    cost: int


@dataclass
class CaseData:
    id: Optional[int]
    name: str
    cost: int
    presents_with_probabilities: List[Tuple[PresentData, float]]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        total_prob = sum(prob for _, prob in self.presents_with_probabilities)
        if not (99.99 <= total_prob <= 100.01):
            raise ValueError(f"Сумма вероятностей для кейса '{self.name}' должна быть 100%, а не {total_prob}%")
    
    def get_random_present(self) -> PresentData:
        rand = random.uniform(0, 100)
        cumulative_prob = 0
        
        for present, prob in self.presents_with_probabilities:
            cumulative_prob += prob
            if rand <= cumulative_prob:
                return present
        
        return self.presents_with_probabilities[-1][0]


class CaseRepository:
    """Репозиторий для работы с кейсами и подарками"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    async def init_tables(self):
        """Инициализация таблиц и начальных данных"""
        await self._seed_initial_data()
    
    async def _seed_initial_data(self):
        """Заполнение начальными данными"""
        count = await self.get_cases_count()
        if count > 0:
            return
        
        initial_cases = [
            {
                "name": "Стартовый кейс",
                "cost": 1000,
                "presents": [
                    (100, 30.0),
                    (200, 50.0),
                    (500, 20.0),
                ]
            },
            {
                "name": "Премиум кейс",
                "cost": 2500,
                "presents": [
                    (500, 40.0),
                    (1000, 35.0),
                    (2000, 20.0),
                    (5000, 5.0),
                ]
            },
            {
                "name": "VIP кейс",
                "cost": 10000,
                "presents": [
                    (2000, 30.0),
                    (5000, 40.0),
                    (10000, 25.0),
                    (50000, 5.0),
                ]
            },
        ]
        
        for case_data in initial_cases:
            await self.create_case(
                name=case_data["name"],
                cost=case_data["cost"],
                presents_with_costs_and_probs=case_data["presents"]
            )
        
        print("✅ Начальные кейсы созданы")
    
    async def _get_or_create_present(self, session, cost: int) -> Present:
        """Получить или создать подарок"""
        stmt = select(Present).where(Present.cost == cost)
        result = await session.execute(stmt)
        present = result.scalar_one_or_none()
        
        if not present:
            present = Present(cost=cost)
            session.add(present)
            await session.flush()  # Получаем ID
        
        return present
    
    async def create_case(self, name: str, cost: int, 
                         presents_with_costs_and_probs: List[Tuple[int, float]]) -> CaseData:
        """Создание нового кейса с подарками"""
        try:
            async with self.db.async_session() as session:
                # Создаем кейс
                case = Case(name=name, cost=cost)
                session.add(case)
                await session.flush()  # Получаем ID кейса
                
                # Создаем связи с подарками и собираем данные для ответа
                presents_data = []
                for cost, prob in presents_with_costs_and_probs:
                    present = await self._get_or_create_present(session, cost)
                    case_present = CasePresent(
                        case_id=case.id,
                        present_id=present.id,
                        probability=prob
                    )
                    session.add(case_present)
                    presents_data.append((PresentData(id=present.id, cost=present.cost), prob))
                
                await session.commit()
                
                return CaseData(
                    id=case.id,
                    name=case.name,
                    cost=case.cost,
                    presents_with_probabilities=presents_data,
                    created_at=case.created_at,
                    updated_at=case.updated_at
                )
                
        except Exception as e:
            print(f"❌ Ошибка создания кейса: {e}")
            raise
    
    async def get_case(self, case_id: int) -> Optional[CaseData]:
        """Получение кейса по ID"""
        try:
            async with self.db.async_session() as session:
                stmt = select(Case).where(Case.id == case_id)
                result = await session.execute(stmt)
                case = result.scalar_one_or_none()
                
                if not case:
                    return None
                
                # Получаем подарки с вероятностями
                stmt = select(CasePresent, Present).join(Present).where(CasePresent.case_id == case_id)
                result = await session.execute(stmt)
                case_presents = result.all()
                
                presents_data = [
                    (PresentData(id=cp.present.id, cost=cp.present.cost), cp.probability)
                    for cp, _ in case_presents
                ]
                
                return CaseData(
                    id=case.id,
                    name=case.name,
                    cost=case.cost,
                    presents_with_probabilities=presents_data,
                    created_at=case.created_at,
                    updated_at=case.updated_at
                )
                
        except Exception as e:
            print(f"❌ Ошибка получения кейса: {e}")
            return None
    
    async def get_all_cases(self) -> Dict[int, CaseData]:
        """Получение всех кейсов"""
        try:
            async with self.db.async_session() as session:
                stmt = select(Case)
                result = await session.execute(stmt)
                cases = result.scalars().all()
                
                cases_dict = {}
                for case in cases:
                    case_data = await self.get_case(case.id)
                    if case_data:
                        cases_dict[case.id] = case_data
                
                return cases_dict
                
        except Exception as e:
            print(f"❌ Ошибка получения всех кейсов: {e}")
            return {}
    
    async def update_case(self, case_id: int, name: Optional[str] = None, 
                         cost: Optional[int] = None, 
                         presents_with_costs_and_probs: Optional[List[Tuple[int, float]]] = None) -> bool:
        """Обновление кейса"""
        try:
            async with self.db.async_session() as session:
                stmt = select(Case).where(Case.id == case_id)
                result = await session.execute(stmt)
                case = result.scalar_one_or_none()
                
                if not case:
                    return False
                
                # Обновляем основные поля
                if name is not None:
                    case.name = name
                if cost is not None:
                    case.cost = cost
                
                # Обновляем подарки если переданы
                if presents_with_costs_and_probs is not None:
                    # Удаляем старые связи
                    stmt = select(CasePresent).where(CasePresent.case_id == case_id)
                    result = await session.execute(stmt)
                    old_case_presents = result.scalars().all()
                    
                    for old_cp in old_case_presents:
                        await session.delete(old_cp)
                    
                    # Создаем новые связи
                    for cost, prob in presents_with_costs_and_probs:
                        present = await self._get_or_create_present(session, cost)
                        case_present = CasePresent(
                            case_id=case.id,
                            present_id=present.id,
                            probability=prob
                        )
                        session.add(case_present)
                
                await session.commit()
                return True
                
        except Exception as e:
            print(f"❌ Ошибка обновления кейса: {e}")
            return False
    
    async def delete_case(self, case_id: int) -> bool:
        """Удаление кейса"""
        try:
            async with self.db.async_session() as session:
                stmt = select(Case).where(Case.id == case_id)
                result = await session.execute(stmt)
                case = result.scalar_one_or_none()
                
                if not case:
                    return False
                
                await session.delete(case)
                await session.commit()
                return True
                
        except Exception as e:
            print(f"❌ Ошибка удаления кейса: {e}")
            return False
    
    async def case_exists(self, case_id: int) -> bool:
        """Проверка существования кейса"""
        try:
            async with self.db.async_session() as session:
                stmt = select(func.count(Case.id)).where(Case.id == case_id)
                result = await session.execute(stmt)
                count = result.scalar()
                return count > 0
        except Exception as e:
            print(f"❌ Ошибка проверки существования кейса: {e}")
            return False
    
    async def get_cases_count(self) -> int:
        """Получение количества кейсов"""
        try:
            async with self.db.async_session() as session:
                stmt = select(func.count(Case.id))
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            print(f"❌ Ошибка подсчета кейсов: {e}")
            return 0


class CaseManager:
    """Менеджер для работы с кейсами"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.repository = CaseRepository(db_manager)
    
    async def initialize(self):
        """Инициализация менеджера кейсов"""
        await self.repository.init_tables()
    
    def validate_case_name(self, name: str) -> tuple[bool, str]:
        """Валидация названия кейса"""
        if not name or len(name.strip()) == 0:
            return False, "Название кейса не может быть пустым"
        if len(name) > 255:
            return False, "Название кейса слишком длинное (максимум 255 символов)"
        return True, ""
    
    def validate_case_cost(self, cost: str) -> tuple[bool, int, str]:
        """Валидация стоимости кейса"""
        try:
            cost_int = int(cost)
            if cost_int <= 0:
                return False, 0, "Стоимость кейса должна быть положительным числом"
            return True, cost_int, ""
        except ValueError:
            return False, 0, "Стоимость кейса должна быть числом"
    
    def validate_present_data(self, text: str) -> tuple[bool, tuple[int, float], str]:
        """Валидация данных подарка (стоимость:вероятность)"""
        try:
            if ':' not in text:
                return False, (0, 0.0), "Формат должен быть 'стоимость:вероятность'"
            
            cost_str, prob_str = text.split(':', 1)
            cost = int(cost_str.strip())
            prob = float(prob_str.strip())
            
            if cost <= 0:
                return False, (0, 0.0), "Стоимость подарка должна быть положительной"
            if prob <= 0 or prob > 100:
                return False, (0, 0.0), "Вероятность должна быть от 0 до 100%"
            
            return True, (cost, prob), ""
        except ValueError:
            return False, (0, 0.0), "Неверный формат числа"
    
    def validate_presents_list(self, presents: List[Tuple[int, float]]) -> tuple[bool, str]:
        """Валидация списка подарков"""
        if not presents:
            return False, "Список подарков не может быть пустым"
        
        total_prob = sum(prob for _, prob in presents)
        if not (99.99 <= total_prob <= 100.01):
            return False, f"Сумма вероятностей должна быть 100%, а не {total_prob}%"
        
        return True, "" 