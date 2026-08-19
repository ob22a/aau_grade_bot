"""Telegram conversation states persisted by Redis storage."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class RegistrationFSM(StatesGroup):
    university_id = State()
    password = State()
    section = State()
    confirm = State()


class AdminBroadcastFSM(StatesGroup):
    message = State()
    confirm = State()


class AccountDeletionFSM(StatesGroup):
    confirm = State()
