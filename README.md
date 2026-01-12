# RuStore Public API Client (Desktop)

Desktop UI-клиент на Python (tkinter) для вызова Public API RuStore.

Назначение:
- ручное тестирование Public API RuStore
- отладка параметров, путей, авторизации
- просмотр реальных запросов/ответов

Поддерживает:
- методы из Subscription Payment API и Product Catalog API
- автоматическое получение auth-токена и его рефреш
- UI для выбора метода и ввода параметров (path / query / body)
- вывод ответа (Pretty / Raw) и логирование всех запросов, включая получение токена
- удобное копирование/вставка (Ctrl+C / Ctrl+V работают на RU и EN раскладке)
- группировка методов по разделам (группа → список методов)

---

# 1. Работа с .exe (для пользователей, без Python)

## 1.1 Что нужно

- файл app.exe  
- файл .env рядом с app.exe (пользователь кладёт свои ключи)  
- файл methods.yaml НЕ нужен, так как он вшит внутрь exe  

---

## 1.2 Подготовка .env

Создайте рядом с app.exe файл .env со следующим содержимым.

```  
RUSTORE_KEY_ID=...  
RUSTORE_PRIVATE_KEY_B64=...  
RUSTORE_BASE_URL=https://public-api.rustore.ru  
RUSTORE_TOKEN_SKEW_SECONDS=30  
HTTP_TIMEOUT_SECONDS=30  
```

Важно:
- значения без кавычек
- без пробелов вокруг =
- private key в одной строке, без переносов

---

## 1.3 Запуск

1. Убедитесь, что app.exe и .env лежат в одной папке  
2. Запустите app.exe двойным кликом  
3. Дождитесь открытия окна приложения  

Python на компьютере **не нужен**.

---

## 1.4 Как работать в приложении

1. Слева выберите метод (группы — заголовки, методы — строки под ними)
2. Заполните PATH параметры
3. Заполните QUERY параметры (если есть)
4. При необходимости заполните BODY (JSON)
5. Нажмите **Вызвать метод**
6. Ответ смотрите во вкладках:
   - Pretty (wrap) — удобное чтение JSON
   - Raw (scroll) — сырой ответ
   - Logs (scroll) — все запросы и ответы, включая авторизацию

---

# 2. Работа как с Python-проектом (для разработчиков)

## 2.1 Требования

- Windows  
- Python 3.14  
- рекомендуется использовать виртуальное окружение (venv)  

---

## 2.2 Установка

```  
python -m venv .venv  
.venv\\Scripts\\activate  
python -m pip install --upgrade pip  
pip install requests python-dotenv pycryptodome pyyaml  
```

---

## 2.3 Настройка ключей

В корне проекта (рядом с app.py) создайте файл .env.

```  
RUSTORE_KEY_ID=...  
RUSTORE_PRIVATE_KEY_B64=...  
RUSTORE_BASE_URL=https://public-api.rustore.ru  
RUSTORE_TOKEN_SKEW_SECONDS=30  
HTTP_TIMEOUT_SECONDS=30  
```

---

## 2.4 Запуск

```  
python app.py  
```

---

# 3. Сборка .exe (для разработчиков)

## 3.1 Установка PyInstaller

``` 
pip install pyinstaller>=6.15.0  
```

---

## 3.2 Сборка one-file exe (с вшитым methods.yaml)

```
pyinstaller --onefile --noconsole app.py --add-data "methods.yaml;."  
```

Результат: dist/app.exe

---

# 4. Структура проекта

Ожидаемая структура:

```  
app.py  
methods.yaml  
rustore/  
  config.py  
  token_manager.py  
  api_client.py  
  methods.py  
  crypto_sig.py  
  resource.py  
.env  
```

---

# 5. Безопасность и Git

В репозиторий добавляем:
- код
- methods.yaml
- README.md
- .env.example

В репозиторий НЕ добавляем:
- .env
- dist
- build
- .venv

Пример .gitignore:

``` 
.env  
.venv/  
__pycache__/  
dist/  
build/  
*.spec  
```

---

# 6. Важно

- Если у метода нет sandbox-версии, он просто не указывается в methods.yaml  
- В этом случае при выборе sandbox будет показана понятная ошибка  
- Это корректное и ожидаемое поведение

---

# 7. Troubleshooting

Если что-то не работает:
1. Открой вкладку Logs
2. Смотри блоки:
   - [AUTH][REQUEST]
   - [AUTH][RESPONSE]
   - [AUTH][ERROR]

В 90% случаев проблема:
- неверный формат private key
- не base64
- лишние пробелы или переносы строк в .env