import random
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database import DatabaseManager, Case, Present, CasePresent


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
            await session.flush()
        
        return present
    
    async def create_case(self, name: str, cost: int, 
                         presents_with_costs_and_probs: List[Tuple[int, float]]) -> CaseData:
        """Создать новый кейс"""
        async with self.db.async_session() as session:
            try:
                new_case = Case(name=name, cost=cost)
                session.add(new_case)
                await session.flush()
                
                presents_data = []
                for present_cost, probability in presents_with_costs_and_probs:
                    present = await self._get_or_create_present(session, present_cost)
                    
                    case_present = CasePresent(
                        case_id=new_case.id,
                        present_id=present.id,
                        probability=probability
                    )
                    session.add(case_present)
                    presents_data.append((PresentData(id=present.id, cost=present_cost), probability))
                
                await session.commit()
                
                print(f"➕ Кейс '{name}' успешно создан")
                
                return CaseData(
                    id=new_case.id,
                    name=new_case.name,
                    cost=new_case.cost,
                    presents_with_probabilities=presents_data,
                    created_at=new_case.created_at,
                    updated_at=new_case.updated_at
                )
                
            except Exception as e:
                await session.rollback()
                print(f"❌ Ошибка при создании кейса: {e}")
                raise
    
    async def get_case(self, case_id: int) -> Optional[CaseData]:
        """Получить кейс по ID"""
        async with self.db.async_session() as session:
            try:
                stmt = select(Case).options(
                    selectinload(Case.case_presents).selectinload(CasePresent.present)
                ).where(Case.id == case_id)
                
                result = await session.execute(stmt)
                case = result.scalar_one_or_none()
                
                if not case:
                    return None
                
                presents_data = []
                for cp in case.case_presents:
                    presents_data.append((
                        PresentData(id=cp.present.id, cost=cp.present.cost),
                        cp.probability
                    ))
                
                return CaseData(
                    id=case.id,
                    name=case.name,
                    cost=case.cost,
                    presents_with_probabilities=presents_data,
                    created_at=case.created_at,
                    updated_at=case.updated_at
                )
                
            except Exception as e:
                print(f"❌ Ошибка при получении кейса: {e}")
                return None
    
    async def get_all_cases(self) -> Dict[int, CaseData]:
        """Получить все кейсы"""
        async with self.db.async_session() as session:
            try:
                stmt = select(Case).options(
                    selectinload(Case.case_presents).selectinload(CasePresent.present)
                )
                
                result = await session.execute(stmt)
                cases = result.scalars().all()
                
                cases_dict = {}
                for case in cases:
                    presents_data = []
                    for cp in case.case_presents:
                        presents_data.append((
                            PresentData(id=cp.present.id, cost=cp.present.cost),
                            cp.probability
                        ))
                    
                    cases_dict[case.id] = CaseData(
                        id=case.id,
                        name=case.name,
                        cost=case.cost,
                        presents_with_probabilities=presents_data,
                        created_at=case.created_at,
                        updated_at=case.updated_at
                    )
                
                return cases_dict
                
            except Exception as e:
                print(f"❌ Ошибка при получении всех кейсов: {e}")
                return {}
    
    async def update_case(self, case_id: int, name: Optional[str] = None, 
                         cost: Optional[int] = None, 
                         presents_with_costs_and_probs: Optional[List[Tuple[int, float]]] = None) -> bool:
        """Обновить кейс"""
        async with self.db.async_session() as session:
            try:
                stmt = select(Case).options(
                    selectinload(Case.case_presents)
                ).where(Case.id == case_id)
                
                result = await session.execute(stmt)
                case = result.scalar_one_or_none()
                
                if not case:
                    print(f"❌ Кейс с ID {case_id} не найден")
                    return False
                
                if name is not None:
                    case.name = name
                
                if cost is not None:
                    case.cost = cost
                
                if presents_with_costs_and_probs is not None:
                    case.case_presents.clear()
                    
                    for present_cost, probability in presents_with_costs_and_probs:
                        present = await self._get_or_create_present(session, present_cost)
                        
                        case_present = CasePresent(
                            case_id=case_id,
                            present_id=present.id,
                            probability=probability
                        )
                        session.add(case_present)
                
                await session.commit()
                print(f"🔄 Кейс с ID {case_id} успешно обновлен")
                return True
                
            except Exception as e:
                await session.rollback()
                print(f"❌ Ошибка при обновлении кейса: {e}")
                return False
    
    async def delete_case(self, case_id: int) -> bool:
        """Удалить кейс"""
        async with self.db.async_session() as session:
            try:
                stmt = select(Case).where(Case.id == case_id)
                result = await session.execute(stmt)
                case = result.scalar_one_or_none()
                
                if not case:
                    print(f"❌ Кейс с ID {case_id} не найден")
                    return False
                
                await session.delete(case)
                await session.commit()
                print(f"🗑️ Кейс с ID {case_id} удален")
                return True
                
            except Exception as e:
                await session.rollback()
                print(f"❌ Ошибка при удалении кейса: {e}")
                return False
    
    async def case_exists(self, case_id: int) -> bool:
        """Проверить существование кейса"""
        async with self.db.async_session() as session:
            try:
                stmt = select(func.count(Case.id)).where(Case.id == case_id)
                result = await session.execute(stmt)
                count = result.scalar()
                return count is not None 
            except Exception as e:
                print(f"❌ Ошибка при проверке существования кейса: {e}")
                return False
    
    async def get_cases_count(self) -> int:
        """Получить количество кейсов"""
        async with self.db.async_session() as session:
            try:
                stmt = select(func.count(Case.id))
                result = await session.execute(stmt)
                return result.scalar() or 0
            except Exception as e:
                print(f"❌ Ошибка при подсчете кейсов: {e}")
                return 0


class CaseManager:
    def __init__(self, db_manager: DatabaseManager):
        self.repository = CaseRepository(db_manager)
    
    async def initialize(self):
        await self.repository.init_tables()
    
    def validate_case_name(self, name: str) -> tuple[bool, str]:
        if not name or len(name.strip()) == 0:
            return False, "Название не может быть пустым"
        if len(name) > 100:
            return False, "Название слишком длинное (максимум 100 символов)"
        return True, ""
    
    def validate_case_cost(self, cost: str) -> tuple[bool, int, str]:
        try:
            cost_int = int(cost)
            if cost_int <= 0:
                return False, 0, "Стоимость должна быть больше 0"
            if cost_int > 1000000:
                return False, 0, "Стоимость слишком большая"
            return True, cost_int, ""
        except ValueError:
            return False, 0, "Введите корректное число"
    
    def validate_present_data(self, text: str) -> tuple[bool, tuple[int, float], str]:
        try:
            parts = text.split()
            if len(parts) != 2:
                return False, (0, 0), "Неверный формат. Используйте: стоимость вероятность"
            
            cost = int(parts[0])
            probability = float(parts[1])
            
            if cost <= 0:
                return False, (0, 0), "Стоимость подарка должна быть больше 0"
            if probability <= 0 or probability > 100:
                return False, (0, 0), "Вероятность должна быть от 0 до 100"
            
            return True, (cost, probability), ""
        except ValueError:
            return False, (0, 0), "Неверный формат данных"
    
    def validate_presents_list(self, presents: List[Tuple[int, float]]) -> tuple[bool, str]:
        if not presents:
            return False, "Нужно добавить хотя бы один подарок"
        
        total_prob = sum(p[1] for p in presents)
        if not (99.99 <= total_prob <= 100.01):
            return False, f"Сумма вероятностей должна быть 100%, а не {total_prob}%"
    
        return True, ""
