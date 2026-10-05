# Unicafe Keskusta widget

A GitHub Action fetches Unicafe's menus a few times a day and writes short text
files to `menu/`. A KWGT widget on an Android home screen displays one of them.

## Files the widget can show
- `menu/today.txt`: every Keskusta Unicafe serving lunch today
- `menu/today-vegan.txt`: vegan dishes only (🌱 = vegan, (🌱) = vegan on request)
- `menu/favourites.txt`: only the restaurants in `FAVOURITES` in `update_menu.py`

Raw URL pattern for KWGT:
`https://raw.githubusercontent.com/<your-username>/<repo>/main/menu/today.txt`

## Settings
Edit the top of `update_menu.py`: language, prices, lunch hours, favourites.
Run it by hand from the Actions tab ("Update Unicafe menu" → "Run workflow").
