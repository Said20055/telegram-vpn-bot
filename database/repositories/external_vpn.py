from sqlalchemy import select, update, delete

from db import ExternalSubscription, ExternalConfig


class ExternalSubscriptionRepository:
    def __init__(self, session_maker):
        self._session_maker = session_maker

    async def create(self, name: str, url: str) -> ExternalSubscription:
        async with self._session_maker() as session:
            sub = ExternalSubscription(name=name, url=url)
            session.add(sub)
            await session.commit()
            await session.refresh(sub)
            return sub

    async def get_all(self) -> list[ExternalSubscription]:
        async with self._session_maker() as session:
            result = await session.execute(select(ExternalSubscription).order_by(ExternalSubscription.added_at.desc()))
            return list(result.scalars().all())

    async def get(self, sub_id: int) -> ExternalSubscription | None:
        async with self._session_maker() as session:
            return await session.get(ExternalSubscription, sub_id)

    async def delete(self, sub_id: int):
        async with self._session_maker() as session:
            await session.execute(delete(ExternalSubscription).where(ExternalSubscription.id == sub_id))
            await session.commit()


class ExternalConfigRepository:
    def __init__(self, session_maker):
        self._session_maker = session_maker

    async def create_many(self, subscription_id: int, configs: list[dict]) -> int:
        """Создать несколько конфигов сразу. configs: [{name, raw_link}, ...]"""
        async with self._session_maker() as session:
            objs = [
                ExternalConfig(subscription_id=subscription_id, name=c["name"], raw_link=c["raw_link"])
                for c in configs
            ]
            session.add_all(objs)
            await session.commit()
            return len(objs)

    async def get_active(self) -> list[ExternalConfig]:
        async with self._session_maker() as session:
            stmt = (
                select(ExternalConfig)
                .join(ExternalSubscription, ExternalConfig.subscription_id == ExternalSubscription.id)
                .where(ExternalConfig.is_active == True)
                .where(ExternalSubscription.is_active == True)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_by_subscription(self, subscription_id: int) -> list[ExternalConfig]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(ExternalConfig).where(ExternalConfig.subscription_id == subscription_id)
            )
            return list(result.scalars().all())

    async def toggle_active(self, config_id: int) -> tuple[bool, int | None]:
        """Переключает is_active. Возвращает (новое_значение, subscription_id)."""
        async with self._session_maker() as session:
            config = await session.get(ExternalConfig, config_id)
            if not config:
                return False, None
            config.is_active = not config.is_active
            sub_id = config.subscription_id
            await session.commit()
            return config.is_active, sub_id

    async def delete(self, config_id: int):
        async with self._session_maker() as session:
            await session.execute(delete(ExternalConfig).where(ExternalConfig.id == config_id))
            await session.commit()
