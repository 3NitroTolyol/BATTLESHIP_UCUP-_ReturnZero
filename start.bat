@echo off
chcp 65001 > nul
echo Ініціалізація Battleship.io...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Помилка: Python не знайдено в системі. Будь ласка, встановіть Python 3.8 або вище.
    pause
    exit
)

if not exist "venv" (
    echo Створення віртуального середовища...
    python -m venv venv
)

echo Активація середовища та перевірка бібліотек...
call venv\Scripts\activate
pip install fastapi uvicorn websockets >nul 2>&1

echo Запуск гри...
start http://127.0.0.1:8000
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000