# Earth Evidence Atlas – prototyp (NASA Space Apps 2026)

Wyzwanie: **Be An Earth System Trend Detective!** Koncepcja: [formalne/05_plan_projektu.md](formalne/05_plan_projektu.md).

Stan na **14.11.2026, ok. 17:30**: działający lokalnie prototyp end-to-end. Obejmuje prawdziwe dane NASA dla 7 zmiennych i 4 regionów oraz **interaktywny glob 3D**, na którym można zaznaczyć dowolny obszar i zlecić obliczenia na żądanie. Do tego silnik statystyczny z testami, API, widok „Trend detective” (mapa, wykres, macierz okresów, eksport) i laboratorium fałszywych alarmów. **Brak deploymentu** (tylko `127.0.0.1`).

## Globe explorer (zakładka startowa)

- Glob 3D (MapLibre GL 5, projekcja globe). Pod spodem zdjęcia **NASA GIBS**: Blue Marble albo zdjęcia historyczne dla wybranego roku i miesiąca, czyli true colour MODIS (dzień), NDVI i LST miesięczne, temperatura MERRA-2, opad IMERG. Data podąża za suwakiem roku. Granice: Natural Earth.
- Tło: prawdziwe gwiazdy z Yale Bright Star Catalogue (dane z pakietu d3-celestial 0.7.35, licencja BSD-3-Clause, plik `web/vendor/stars.json`, ok. 5000 gwiazd do jasności 6 mag). Rysujemy niebo widoczne za globem z danego kierunku, dla bieżącego czasu gwiazdowego (GMST). Bieguny (powyżej 85°, których MapLibre nie rysuje) mają naturalny kolor zdjęcia pod spodem, rozmyty i płynnie wygładzony do jednej średniej barwy, zamiast rozciągniętych pikseli. Czapa zmienia się razem z wybraną warstwą zdjęć.
- Animacja „Year by year” podmienia obraz klatki w miejscu (`updateImage`) i pobiera kolejne lata z wyprzedzeniem. Zdjęcia NASA zmieniają się przez płynne przejście między dwiema warstwami, bez czarnego mignięcia.
- Warstwa danych: **trend** (z wyciszeniem komórek nieistotnych po FDR) albo **rok po roku**, czyli anomalia roczna względem średniej z całego okresu, z przyciskiem ▶ do animacji.
- Dymek po najechaniu pokazuje wartość, p i istotność. Klik w komórkę analizuje tę komórkę.
- **„Select an area to analyse”:** prostokąt na globie → wybór zbioru danych lub modelu → „Analyse this area”.
  - Jeśli obszar mieści się w już zbudowanej kostce, wynik pojawia się od razu.
  - Jeśli nie, backend uruchamia zadanie pobrania i przetworzenia danych NASA. Pasek postępu działa przez `POST /api/compute` + `GET /api/jobs/{id}`. Nowy obszar zapisuje się w `data/custom_regions.json` i pojawia na globie jako ★.
  - Limity: MODIS do 8° na bok i 40 deg² (ok. 30–60 s dla 2°×2°); POWER do 30° na bok (kilka sekund); GISTEMP obejmuje cały świat, więc nie trzeba nic pobierać.
- „Open full analysis →” przenosi zaznaczenie do zakładki Trend detective.

> **Ujawnienie AI (wymagane przez Project Submission Guide):** cały kod w `atlas/`, `web/`, `scripts/` i `tests/` wygenerował asystent AI Claude (Anthropic) na prośbę zespołu. Pliki mają to oznaczone w nagłówkach, kostki danych w atrybutach NetCDF (`generator`). Liczby w aplikacji pochodzą wyłącznie z obliczeń na cytowanych danych NASA. Zespół musi przejrzeć kod i opisać użycie AI w zgłoszeniu.

## Uruchomienie

```bash
cd /storage/home/moai/nasaapps && scripts/run.sh 8765
```

Potem w przeglądarce otwórz http://127.0.0.1:8765. Przy zdalnym serwerze użyj tunelu, np. `ssh -L 8765:127.0.0.1:8765 …`.

Pełna przebudowa danych (ok. 10 min, bez logowania; kostki już są w `data/cubes/`):

```bash
cd /storage/home/moai/nasaapps && .venv/bin/python -m scripts.build_data --force
```

Testy (31 zielonych):

```bash
cd /storage/home/moai/nasaapps && .venv/bin/python -m pytest -q tests
```

Instalacja od zera: `uv venv .venv --python 3.11 && uv pip install -r requirements.txt`.

## Co jest zrobione

| Warstwa | Pliki | Opis |
| --- | --- | --- |
| Katalog | [atlas/config.py](atlas/config.py) | 6 zmiennych (pytanie dla ucznia, definicja, jednostki, cytowanie, licencja, zastrzeżenia) i 4 regiony |
| Dane | [atlas/sources/](atlas/sources/) | Adaptery: MODIS przez Planetary Computer, NASA POWER, GISTEMP. Wyjście: kostki NetCDF `(time, lat, lon)` z metadanymi pochodzenia |
| Statystyka | [atlas/stats.py](atlas/stats.py) | Deseasonalizacja, OLS z korektą AR(1) (Santer 2000), sezonowy Mann–Kendall i Sen, FDR Benjamini–Hochberg, średnia ważona cos(lat), macierz okien, werdykt |
| API | [atlas/api.py](atlas/api.py) | `/api/catalog`, `/api/analysis`, `/api/map`, `/api/export.csv`, `/api/export.json`, `/api/simulate`, `/api/simulate_many` |
| Frontend | [web/](web/) | Vanilla JS + Leaflet + Plotly, bez kroku budowania. Podkład mapy: NASA GIBS Blue Marble. Stan analizy zapisany w URL (`#var=…&region=…`) |
| Testy | [tests/](tests/) | Walidacja statystyki na danych syntetycznych (m.in. odsetek fałszywych alarmów przy autokorelacji) i smoke testy API na wszystkich kostkach |

### Dane (wszystkie bez Earthdata Login)

| id | Zmienna | Źródło | Siatka | Lata | Regiony |
| --- | --- | --- | --- | --- | --- |
| `ndvi` | NDVI | MOD13A1 v061 (Terra), COG z Planetary Computer | 0,1° | 2001–2024 | 3 regiony |
| `lst_day` | LST dzienna | MOD11A2 v061 (Terra), COG z Planetary Computer | 0,1° | 2001–2024 | 3 regiony |
| `t2m` | Temperatura powietrza 2 m | NASA POWER (MERRA-2) | 0,5°×0,625° | 1981–2025 | 3 regiony |
| `precip` | Opad | NASA POWER PRECTOTCORR (MERRA-2) | 0,5°×0,625° | 1981–2025 | 3 regiony |
| `soil_root` | Wilgotność strefy korzeniowej | NASA POWER GWETROOT (MERRA-2) | 0,5°×0,625° | 1981–2025 | 3 regiony |
| `lst_day_aqua` | LST popołudniowa (kontrola) | MYD11A2 v061 (Aqua, 13:30) | 0,1° | 2003–2024 | 3 regiony |
| `gistemp` | Anomalia temperatury | NASA GISS GISTEMP v4 | 2° | 1951–2025 | świat + 3 regiony |

Regiony: `central_europe` (14–24°E, 49–55°N), `nw_india` (72–78°E, 26–31°N), `amazon_arc` (64–54°W, 13–7°S), `world`.

**Odstępstwo od planu:** plan P0 zakładał MOD13C2, MOD11C3 i IMERG. Te produkty wymagają NASA Earthdata Login, a na serwerze nie ma `~/.netrc`. Dlatego użyłem tych samych misji (MODIS Terra v061) w wersjach 500 m / 1 km z publicznego mirrora COG, a opad wziąłem z MERRA-2 przez POWER. IMERG jest do zrobienia (niżej).

## Wyniki do historii demo (policzone przez narzędzie, do sprawdzenia przez zespół)

Domyślny okres zmiennej, cały region, 95% CI, p z korektą autokorelacji:

- **NW Indie: „zieleń a woda”.** NDVI rośnie o +0,036/dekadę [0,028; 0,043]. Dzienna LST *spada* o −0,72 °C/dekadę [−1,10; −0,35] (2001–2024), a letnia T2M w MERRA-2 o −0,32 °C/dekadę. To spójne z opisywanym w literaturze chłodzeniem przez nawadnianie, ale **nie jest to wniosek przyczynowy**. Wilgotność gleby w MERRA-2 rośnie, ale model nie zna poboru wód podziemnych, więc to dobra lekcja ograniczeń modelu. GRACE (P1) mógłby pokazać kontrast.
- **Amazonia, łuk wylesiania.** Dzienna LST latem +0,58 °C/dekadę, a mapa pokazuje wyraźne ogniska zgodne z wylesianiem. NDVI w JJA spada o −0,022/dekadę. Wilgotność gleby spada.
- **Europa Środkowa: „czy wniosek się trzyma”.** NDVI całoroczny jest istotny (+0,034), ale w samym lecie JJA przedział obejmuje zero. Do tego Sen 0,018 vs OLS 0,034, więc trend prawdopodobnie napędzają zimowe miesiące (śnieg). To dobry przykład na lekcję o sezonach. LST +0,88 °C/dekadę, T2M +0,51 °C/dekadę (1981–2025). Opad: brak wykrywalnego trendu.
- **Świat (GISTEMP):** +0,162 °C/dekadę [0,149; 0,176] w latach 1951–2025, 13 756 z 15 914 komórek istotnych po FDR. Mapa pokazuje wzmocnienie arktyczne.

⚠️ **Wynik sprawdzenia dryfu (Terra vs Aqua, LST dzienna):**

| Region | Terra 2003–2021 | Terra 2003–2024 | Aqua 2003–2021 | Aqua 2003–2024 |
| --- | --- | --- | --- | --- |
| NW Indie | −0,29 (p = 0,22) | −0,70 (p = 0,001) | −0,38 (p = 0,15) | −0,52 (p = 0,02) |
| Europa Środkowa | +1,10 (p = 0,006) | +0,90 (p = 0,004) | +1,10 (p = 0,006) | +1,08 (p < 0,001) |
| Amazonia | +0,56 (p < 0,001) | +0,40 (p < 0,001) | +0,50 (p < 0,001) | +0,58 (p < 0,001) |

Wartości w °C/dekadę. Wniosek: ochłodzenie w NW Indiach jest **nieistotne do 2021 r.** u obu satelitów i staje się istotne dopiero po dodaniu lat 2022–2024. W tych latach dryfowały obie orbity, ale mogły to też być rzeczywiście chłodniejsze lata. W demo pokazywać to jako przykład **„direction holds, significance depends on period”**, a nie jako odkrycie. Europa i Amazonia są odporne: oba satelity i oba okna dają ten sam wynik.

⚠️ **Do weryfikacji przed pokazaniem:** opad MERRA-2 w Amazonii wychodzi −0,57 mm/dzień/dekadę, czyli podejrzanie dużo (trendy opadu w reanalizach bywają artefaktami). Nie używać w demo bez porównania z IMERG/GPCP.

## Znane ograniczenia (świadome uproszczenia prototypu)

- MODIS jest czytany z overview COG (ok. 4 km) **bez warstwy QA** (`pixel_reliability` / `QC_Day`). Odrzucane są tylko wartości spoza zakresu. Następny krok to wczytanie QA na tym samym poziomie overview i maskowanie.
- Wartość miesięczna MODIS to średnia kompozytów zaczynających się w danym miesiącu (granice miesięcy są przybliżone).
- Korekta Santera jest lekko liberalna dla krótkich serii: przy 10 latach i φ = 0,7 daje ok. 7% fałszywych alarmów zamiast 5%. Laboratorium pokazuje to uczciwie.
- Klimatologia do anomalii liczona jest z wybranego okresu, a nie ze stałej bazy 2001–2020.
- Brak GPU: obliczenia numpy trwają poniżej 0,1 s na zapytanie dla obecnych siatek, więc GPU nie jest jeszcze potrzebne.
- Rysowanie prostokąta i klik w komórkę analizują tylko obszar wewnątrz zbudowanego regionu. Dowolnych regionów (pobieranie na żądanie) jeszcze nie ma.
- Frontend jest po angielsku (wymóg zgłoszenia). Nie testowano dostępności czytnikiem ekranu.

## Czego jeszcze potrzebujemy (propozycja kolejności)

1. **Przegląd kodu przez zespół** i decyzja co do ujawnienia AI (patrz [formalne/02_zasady_hackathonu.md](formalne/02_zasady_hackathonu.md#6-użycie-narzędzi-aisi)).
2. **Live demo (konieczne do zgłoszenia):** publiczny URL bez logowania, najlepiej przed 15.11 rano. To jeden proces uvicorn + statyczne pliki + ok. 60 MB kostek; `data/raw` nie jest potrzebne. Do ustalenia: gdzie hostujemy (VM, kontener, tunel z tego serwera) i czy publiczne demo ma pozwalać na obliczenia na żądanie. Rekomenduję limit kolejki i rozmiaru; na razie zadania nie mają limitu liczby ani czasu.
3. **Materiały zgłoszenia:** film ≤ 30 s (glob → zaznaczenie Amazonii → wynik → macierz) albo ≤ 7 slajdów po angielsku, opis projektu, lista źródeł i licencji, oznaczenie AI.
4. **Earthdata Login** (`~/.netrc`), potem adapter IMERG monthly. Zastąpi wątpliwy opad MERRA-2 w Amazonii i da zmienną zgodną z planem P0.
5. QA dla MODIS (`pixel_reliability` / `QC_Day`).
6. P1: GRACE (magazyn wody) dla NW Indii, czyli dokładnie kontrast „zieleń vs woda”. Ewentualnie zlewnie HydroBASINS zamiast prostokątów.
7. Drobne: obszary przez linię zmiany daty, tłumaczenie UI, dostępność, test na telefonie.

## Wygląd i ikony (14.11 wieczorem)

- Logo w nagłówku jest pisane fontem **Nasalization** (Ray Larabie, freeware 1997; plik `web/fonts/nasalization.ttf`, skopiowany z załącznika Mai). Wzdłuż krawędzi liter pojawia się jedna iskierka naraz, w losowym miejscu. Przy włączonym w systemie ograniczeniu animacji (`prefers-reduced-motion`) iskierka jest wyłączona.
- Ikony są w jednym pliku `web/icons.svg` (sprite z elementami `<symbol id="i-…">`). Ikony dostarczył zespół. Żeby podmienić ikonę, wklej nowy SVG do środka `<symbol>` i zostaw jego `id`. Kolor ikony bierze się z `currentColor`.
- Pokazywanie danych na globie włącza i wyłącza przełącznik, a nie ikona. Na zakładce Globe nie ma stopki; na pozostałych stopka ma 11 px.
- Jeden styl dymków (`#tip`) obsługuje glob, mapę Leaflet, wykresy Plotly (ich własne dymki i pasek narzędzi są wyłączone) oraz przyciski-ikony (atrybut `data-tip`).
- Kontrast tekstu jest sprawdzany według progu WCAG AA (4.5:1) we wszystkich zakładkach, w trybie jasnym i ciemnym.

## Obszary użytkowników i mapa w Detective (14.11 w nocy)

- **Kto widzi które obszary:** obszary policzone na globie są wspólne na serwerze, ale każdy odwiedzający domyślnie widzi tylko własne (zapamiętane w przeglądarce). Przełącznik „Areas from others” pokazuje też obszary innych. Krzyżyk na obszarze ukrywa go tylko u tego użytkownika i nie kasuje go nikomu innemu. Obszarów wbudowanych nie da się ukryć.
- **Sprzątanie na publicznym serwerze:** uruchom serwer z `ATLAS_PRUNE_DAYS=7 ATLAS_MAX_CUSTOM=60`. Serwer usunie wtedy obszary nieużywane od 7 dni oraz najstarsze ponad limit 60, razem z ich plikami. Domyślnie sprzątanie jest wyłączone, więc lokalna kopia nigdy niczego nie kasuje.
- **Mapa w Detective:**
  - Siatka danych jest rysowana jako jeden obraz, więc nie ma już artefaktów przy oddalaniu.
  - Narzędzia „zaznacz obszar” i „cały region” są na samej mapie, w prawym górnym rogu.
  - W trybie zaznaczania widać baner, a ramka mapy jest podświetlona. Esc albo „Cancel” przerywa zaznaczanie; Esc działa też na globie.

## Odpowiedzi na pytania w Detective

- Po kliknięciu pytania pod rzędem pytań pojawia się karta **Answer**. Zawiera:
  - krótką odpowiedź, np. „Yes – warmer.”, „We can't tell yet.” albo „It depends on the period.”,
  - zdanie z wynikiem: kierunek, tempo zmiany, okres i pora roku,
  - całkowitą zmianę w porównaniu z typowymi wahaniami rok do roku (i jako % zwykłego poziomu przy NDVI, opadzie i wilgotności gleby),
  - udział komórek mapy, które rosną, maleją i mają istotny trend,
  - pewność wyniku: ile innych okresów daje ten sam kierunek i czy test Manna–Kendalla potwierdza trend,
  - jedno najważniejsze zastrzeżenie do źródła danych,
  - rozwijane „How we know” z liczbami.
- Pytanie o drugiego satelitę (Aqua) porównuje wynik z Terrą dla tego samego obszaru i okresu.
- Pytanie „Where is it warming fastest?” wskazuje komórkę z najszybszym istotnym ociepleniem.
- **Bez modelu językowego:** odpowiedzi to stałe szablony w `atlas/answers.py` wypełniane liczbami z analizy. Odpowiedź trafia też do eksportu JSON (`answer`) i ma testy w `tests/test_answers.py`. Nie podaje przyczyn zmian.
