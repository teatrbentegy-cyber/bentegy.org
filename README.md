# bentegy.org

Сайт Театру Бентеги / Bentegy Theatre website.

- Редагування вмісту: https://bentegy.org/admin/ (вхід через GitHub-токен)
- Вміст: `content/` (афіша, вистави, сторінки), фото: `static/uploads/`
- Збірка: `python build/build.py` → `public/`; публікує GitHub Actions автоматично після кожної зміни і щодня о 03:00 UTC (минулі покази зникають самі)
