from init_db import init
from app import app

if __name__ == '__main__':
    init()
    print("\n=== Цифровой архив ИМТ им. Н.М. Загурского ===")
    print("Сервер запущен: http://localhost:5000")
    print("Логин: admin | Пароль: admin123")
    print("Нажмите Ctrl+C для остановки.\n")
    app.run(debug=False, host='0.0.0.0', port=5000)
