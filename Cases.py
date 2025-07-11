import random
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional


@dataclass
class Present:
    cost: int


@dataclass
class Case:
    id: int
    name: str
    cost: int
    presents_with_probabilities: List[Tuple[Present, float]]

    def __post_init__(self):
        total_prob = sum(prob for _, prob in self.presents_with_probabilities)
        if not (99.99 <= total_prob <= 100.01):
            raise ValueError(f"Сумма вероятностей для кейса '{self.name}' должна быть 100%, а не {total_prob}%")

    def get_random_present(self) -> Present:
        rand = random.uniform(0, 100)
        cumulative_prob = 0

        for present, prob in self.presents_with_probabilities:
            cumulative_prob += prob
            if rand <= cumulative_prob:
                return present

        return self.presents_with_probabilities[-1][0]


class CaseRepository:
    _cases: Dict[int, Case] = {
        1: Case(
            id=1,
            name="Стартовый кейс",
            cost=1000,
            presents_with_probabilities=[
                (Present(100), 30.0),
                (Present(200), 50.0),
                (Present(500), 20.0),
            ]
        ),
        2: Case(
            id=2,
            name="Премиум кейс",
            cost=2500,
            presents_with_probabilities=[
                (Present(500), 40.0),
                (Present(1000), 35.0),
                (Present(2000), 20.0),
                (Present(5000), 5.0),
            ]
        ),
        3: Case(
            id=3,
            name="VIP кейс",
            cost=10000,
            presents_with_probabilities=[
                (Present(2000), 30.0),
                (Present(5000), 40.0),
                (Present(10000), 25.0),
                (Present(50000), 5.0),
            ]
        ),
    }

    @staticmethod
    def get_case(case_id: int) -> Optional[Case]:
        return CaseRepository._cases.get(case_id)
    
    @staticmethod
    def get_all_cases() -> Dict[int, Case]:
        return CaseRepository._cases.copy()
    
    @staticmethod
    def case_exists(case_id: int) -> bool:
        return case_id in CaseRepository._cases


def get_random_gift(case_id: int) -> Present:
    case = CaseRepository.get_case(case_id)
    if not case:
        raise ValueError(f"Кейс с ID {case_id} не существует")
    return case.get_random_present()


def get_case_info(case_id: int) -> Dict:
    case = CaseRepository.get_case(case_id)
    if not case:
        raise ValueError(f"Кейс с ID {case_id} не существует")
    
    return {
        "id": case.id,
        "name": case.name,
        "cost": case.cost,
        "possible_rewards": [
            {"cost": present.cost, "probability": prob}
            for present, prob in case.presents_with_probabilities
        ]
    }


def get_all_cases_info() -> List[Dict]:
    return [get_case_info(case_id) for case_id in CaseRepository._cases.keys()]
