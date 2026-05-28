from db import DatabaseManager
import os

_db_instance = None


async def get_db():
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
        await _db_instance.connect()
    yield _db_instance


async def init_db():
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
        await _db_instance.init_db()


async def close_db():
    global _db_instance
    if _db_instance:
        await _db_instance.close()
        _db_instance = None
