import os
from pathlib import Path
from .repo import OrderRepository

class OrderService(BaseService):
    retries: int = 3

    def __init__(self, repo: OrderRepository):
        self.repo = repo

    def find_open(self, customer_id: str) -> list:
        all_orders = self.repo.find_by_customer(customer_id)
        validate(all_orders)
        return _filter_open(all_orders)

    @staticmethod
    def close():
        Path(os.getcwd()).exists()

def _filter_open(orders):
    return [o for o in orders if o.is_open()]

async def main():
    svc = OrderService(OrderRepository())
    return svc.find_open("c1")
