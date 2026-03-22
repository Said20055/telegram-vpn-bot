from database.repositories.stats import StatsRepository
from database.repositories.payment import PaymentRepository
from marzban.init_client import MarzClientCache


class AdminStatsService:
    def __init__(self, stats_repo: StatsRepository, marzban: MarzClientCache,
                 payment_repo: PaymentRepository):
        self._stats_repo = stats_repo
        self._marzban = marzban
        self._payment_repo = payment_repo

    async def get_dashboard_stats(self) -> dict:
        """Агрегирует статистику из БД и Marzban для админ-панели."""
        return {
            "total_users": await self._stats_repo.count_all_users(),
            "active_subs": await self._stats_repo.count_active_subscriptions(),
            "first_payments": await self._stats_repo.count_users_with_first_payment(),
            "users_today": await self._stats_repo.count_new_users_for_period(1),
            "users_week": await self._stats_repo.count_new_users_for_period(7),
            "users_month": await self._stats_repo.count_new_users_for_period(30),
            "system_stats": await self._marzban.get_system_stats(),
            "nodes": await self._marzban.get_nodes(),
            # Revenue stats
            "revenue_today": await self._payment_repo.get_revenue_stats(1),
            "revenue_week": await self._payment_repo.get_revenue_stats(7),
            "revenue_month": await self._payment_repo.get_revenue_stats(30),
            "revenue_total": await self._payment_repo.get_total_revenue(),
        }
