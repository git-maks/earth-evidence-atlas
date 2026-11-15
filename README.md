# Earth Evidence Atlas – prototyp (NASA Space Apps 2026)

Wyzwanie: **Be An Earth System Trend Detective!** Koncepcja: [formalne/05_plan_projektu.md](formalne/05_plan_projektu.md).

Stan na **14.11.2026, ok. 17:30**: działający lokalnie prototyp end-to-end. Obejmuje prawdziwe dane NASA dla 7 zmiennych i 4 regionów oraz **interaktywny glob 3D**, na którym można zaznaczyć dowolny obszar i zlecić obliczenia na żądanie. Do tego silnik statystyczny z testami, API, widok „Trend detective” (mapa, wykres, macierz okresów, eksport) i laboratorium fałszywych alarmów. **Brak deploymentu** (tylko `127.0.0.1`).

## Prezentacja – osobne repozytorium

Prezentację przeniesiono do **`earthatlas.github.io/`**, samodzielnego repo Git ignorowanego przez ten projekt. Otwórz lokalny `earthatlas.github.io/index.html`. Folder zawiera wszystkie zasoby, migawkę wyników, aktualny siedmiostronicowy PDF oraz własne README. Nie jest submodułem i nie trafia do commitów aplikacji.

Repo organizacji: **[EarthAtlas/earthatlas.github.io](https://github.com/EarthAtlas/earthatlas.github.io)**; opublikowana prezentacja: **https://earthatlas.github.io/**. GitHub wymaga małych liter w nazwie repo strony organizacji. Workflow w osobnym repo buduje statyczny katalog `_site/` i publikuje przez GitHub Actions po pushu do `main`. Zwykły build nie potrzebuje checkoutu aplikacji, API ani dostępu do NASA. Pages korzysta ze źródła GitHub Actions i wymusza HTTPS; pierwsze wdrożenie zakończyło się sukcesem 15.11.2026. PDF jest dostępny pod **https://earthatlas.github.io/earth-evidence-atlas.pdf**. Konfigurację i kolejne aktualizacje opisuje README prezentacji.

Kod aplikacji powinien mieć osobne repo, np. `EarthAtlas/earth-evidence-atlas`. GitHub Pages obsługuje prezentację; backend FastAPI potrzebuje własnego hostingu. Po sklonowaniu samej aplikacji prezentację klonuje się osobno do ignorowanego folderu.

```bash
python3 earthatlas.github.io/publish.py
# podgląd artefaktu: python3 -m http.server 8773 --directory earthatlas.github.io/_site
```

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

> **Zasady AI:** według zasad organizatorów nie ma żadnych ograniczeń w używaniu AI i nie trzeba informować, kiedy ani gdzie AI zostało użyte; pełna dowolność. Liczby w aplikacji pochodzą wyłącznie z obliczeń na cytowanych danych NASA (to nasza zasada jakości, nie wymóg hackathonu).

## Resilience (15.11.2026)

**Environmental Resilience Brief** zestawia trendy temperatury powietrza, temperatury powierzchni lądu, opadu i wilgotności gleby w strefie korzeniowej dla jednego obszaru, okresu i sezonu. Wybierz region z listy lub użyj **Open in Resilience** w Globe albo Detective. Raport czyta istniejące kostki, ustala wspólny zakres na podstawie dostępnych danych i wskazuje braki osobno na każdej karcie. Porównania źródeł korzystają z tej samej analizy co Detective, m.in. GPCP dla opadu i Aqua dla temperatury powierzchni.

**Open in Detective** otwiera pełną analizę wybranej zmiennej z tymi samymi parametrami. **Copy link** zachowuje wybór, **CSV** i **JSON** przez `GET /api/resilience` zapisują wyniki, metody, źródła i ograniczenia, a **Print / PDF** drukuje raport. Raport opisuje regionalną ekspozycję i pomaga wybrać miejsca do dalszej oceny infrastruktury cywilnej lub obronnej. Szczegóły zakresu są w [Dodatku D](formalne/07_ocena_i_plan_usprawnien.md#dodatek-d-zakładka-resilience--zastosowania-cywilne-i-obronne-do-p2-8).

## Uruchomienie

```bash
cd /storage/home/moai/nasaapps && scripts/run.sh 8765
```

Potem w przeglądarce otwórz http://127.0.0.1:8765. Przy zdalnym serwerze użyj tunelu, np. `ssh -L 8765:127.0.0.1:8765 …`.

Pełna przebudowa danych (ok. 10 min, bez logowania; kostki już są w `data/cubes/`):

```bash
cd /storage/home/moai/nasaapps && .venv/bin/python -m scripts.build_data --force
```

Testy (54 zielone, w tym kalibracja testów trendu na danych syntetycznych):

```bash
cd /storage/home/moai/nasaapps && .venv/bin/python -m pytest -q tests
```

Instalacja od zera: `uv venv .venv --python 3.11 && uv pip install -r requirements.txt`.

## Co jest zrobione

| Warstwa | Pliki | Opis |
| --- | --- | --- |
| Katalog | [atlas/config.py](atlas/config.py) | 6 zmiennych (pytanie dla ucznia, definicja, jednostki, cytowanie, licencja, zastrzeżenia) i 4 regiony |
| Dane | [atlas/sources/](atlas/sources/) | Adaptery: MODIS przez Planetary Computer, NASA POWER, GISTEMP. Wyjście: kostki NetCDF `(time, lat, lon)` z metadanymi pochodzenia |
| Statystyka | [atlas/stats.py](atlas/stats.py) | Deseasonalizacja, OLS z korektą pamięci danych w dwóch skalach (miesiąc do miesiąca i rok do roku, test przecięcia–sumy), Mann–Kendall z korektami Hirscha–Slacka i Hameda–Rao, Sen, FDR Benjamini–Hochberg, średnia ważona cos(lat), macierz okien, werdykt. Szczegóły i kalibracja: sekcja „Metody statystyczne i kalibracja” |
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

**Odstępstwo od planu:** plan P0 zakładał MOD13C2, MOD11C3 i IMERG. Te produkty wymagają NASA Earthdata Login, a na serwerze nie ma `~/.netrc`. Dlatego użyłem tych samych misji (MODIS Terra v061) w wersjach 500 m / 1 km z publicznego mirrora COG, a opad wziąłem z MERRA-2 przez POWER. IMERG jest do zrobienia (niżej). **Od 15.11** opad MERRA-2 sprawdzamy niezależnym GPCP v2.3 (satelity + deszczomierze, bez logowania), patrz „Walidacja danych”.

## Wyniki do historii demo (policzone przez narzędzie, do sprawdzenia przez zespół)

Domyślny okres zmiennej, cały region, 95% CI, p z korektą autokorelacji:

> **Aktualizacja 15.11 (kalibracja testów):** liczby poniżej policzono starą, zbyt liberalną metodą. Nachylenia się nie zmieniły, ale przedziały są szersze, a niektóre werdykty łagodniejsze. Najważniejsze zmiany: T2M Europa Środkowa +0,51 °C/dekadę, CI **[0,25; 0,77]** (wcześniej [0,35; 0,67]), werdykt nadal „Trend detected”. LST NW Indie i LST Europa Środkowa mają teraz werdykt **„Direction holds, significance varies”**. GISTEMP: CI [0,132; 0,192], 12 602 z 15 914 komórek po FDR. Pełne porównanie: sekcja „Metody statystyczne i kalibracja”.

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

✅ **Rozstrzygnięte 15.11 (sekcja „Walidacja danych”):** GPCP potwierdza kierunek, wielkość z MERRA-2 jest prawdopodobnie zawyżona. Wcześniej: opad MERRA-2 w Amazonii wychodzi −0,57 mm/dzień/dekadę, czyli podejrzanie dużo (trendy opadu w reanalizach bywają artefaktami). Nie używać w demo bez porównania z IMERG/GPCP.

## Znane ograniczenia (świadome uproszczenia prototypu)

- ~~MODIS bez warstwy QA~~ – **naprawione 15.11**: odczyt w natywnej rozdzielczości z maską jakości (sekcja „Walidacja danych”).
- Wartość miesięczna MODIS to średnia kompozytów zaczynających się w danym miesiącu (granice miesięcy są przybliżone).
- Testy trendu są skalibrowane (sekcja niżej), ale **powolnych naturalnych wahań trwających dekady nie da się w pełni odróżnić od trendu na podstawie jednego krótkiego zapisu**: w najtrudniejszym scenariuszu syntetycznym fałszywe alarmy spadły z 12–39% do 5–12%, a nie do 5%. Dla okresów krótszych niż 15 lat odpowiedź pokazuje osobne ostrzeżenie.
- Klimatologia do anomalii liczona jest z wybranego okresu, a nie ze stałej bazy 2001–2020.
- Brak GPU: obliczenia numpy trwają poniżej 0,1 s na zapytanie dla obecnych siatek, więc GPU nie jest jeszcze potrzebne.
- Rysowanie prostokąta i klik w komórkę analizują tylko obszar wewnątrz zbudowanego regionu. Dowolnych regionów (pobieranie na żądanie) jeszcze nie ma.
- Frontend jest po angielsku (wymóg zgłoszenia). Nie testowano dostępności czytnikiem ekranu.

## Metody statystyczne i kalibracja (15.11)

**Problem, który usunęliśmy.** Poprzedni sezonowy test Manna–Kendalla sumował wariancje miesięcy tak, jakby były niezależne. Przy pamięci danych (φ = 0,7) uznawał za istotne ok. 39% szeregów **bez trendu**. Zdanie „Mann–Kendall agrees” nie było więc niezależnym potwierdzeniem. Stary OLS z korektą Santera dawał 6–8% przy szumie AR(1), ale **12–39%** przy powolnych wahaniach trwających lata, bo patrzył tylko na pamięć z miesiąca na miesiąc.

**Obecna metoda** ([atlas/stats.py](atlas/stats.py)):

1. **OLS na anomaliach** (bez zmian: nachylenie, wykres, jednostki).
2. **Pamięć z miesiąca na miesiąc:** AR(1), ale korelację liczymy tylko z par naprawdę odległych o jeden miesiąc. Ma to znaczenie przy sezonach (np. JJA: sierpień → czerwiec to 10 miesięcy) i lukach. Korelacja ma poprawkę obciążenia dla krótkich szeregów po usunięciu trendu: E[r] ≈ ρ − (2 + 4ρ)/n (Marriott i Pope 1954; współczynniki sprawdziliśmy Monte Carlo). Wariancję nachylenia liczymy dokładnie dla rzeczywistego układu próbek (forma kwadratowa Σ wᵢwⱼρ^|kᵢ−kⱼ|). Dla pełnego szeregu daje to wzór Santera i in. (2000).
3. **Pamięć z roku na rok:** ten sam test na średnich sezonowo-rocznych. Grudzień w DJF należy do zimy następnego roku. Ten test wyłapuje powolną zmienność, której AR(1) miesięczny nie widzi.
4. **Łączenie (test przecięcia–sumy, Berger 1982):** p = większe z dwóch p, przedział 95% = suma obu przedziałów. „Istotne” oznacza istotne w obu skalach.
5. **Test rangowy:** sezonowy Mann–Kendall z korektą Hirscha i Slacka (1984) między miesiącami (z wersją dla braków danych) oraz Mann–Kendall na średnich rocznych z korektą Hameda i Rao (1998). Podajemy większe p. Sen slope bez zmian.
6. **Werdykt rozdziela trzy fakty:** istotność w tym okresie, stabilność kierunku (≥ 80% okien) i stabilność istotności. Tę ostatnią liczymy tylko na **długich oknach**, czyli ≥ 3/4 badanego okresu, bo krótkie okna mają małą moc nawet przy prawdziwym trendzie. Nowy kod: `significance_depends_on_period`. Okna się nakładają, więc nie są niezależnymi powtórzeniami. Mówi o tym UI i zakładka Methods.
7. Mapy, macierz okien i laboratorium używają tej samej procedury co wynik główny.

**Kalibracja (Monte Carlo, 1000 szeregów bez trendu na scenariusz, błąd ok. ±0,7 pp).** Scenariusze: AR(1) φ ∈ {0; 0,3; 0,6; 0,9}, 10/24/45 lat, cały rok/JJA/DJF, 0% lub 20% luk, zmienna wariancja w ciągu roku.

| Test | Odsetek fałszywych alarmów (cel 5%) |
| --- | --- |
| Stary sezonowy Mann–Kendall | 2–67% (39% przy φ = 0,7) |
| Stary OLS + Santer | 3–9% |
| **Nowy OLS (dwie skale)** | **1,6–5,0%**, wyjątkowo 6,5% (10 lat, φ = 0,9, 20% luk) |
| **Nowy Mann–Kendall (dwie skale)** | **0,5–6,6%** |
| Powolne wahania (AR(1) + składnik φ = 0,97): stary OLS → nowy | 12–39% → 5–12% |

Koszt: mniejsza moc. Przy φ = 0,6, 24 latach i trendzie 0,4 σ/dekadę wykrywalność spada z ok. 63% do ok. 50%. To uczciwa cena: krótki szereg z pamięcią niesie mniej niezależnej informacji. Testy kalibracji są w [tests/test_stats.py](tests/test_stats.py) i przechodzą przy każdym `pytest`.

**Zmiany na prawdziwych danych** (domyślny okres, cały region):

| Przypadek | Było | Jest |
| --- | --- | --- |
| T2M Europa Środkowa 1981–2025 | +0,51 [0,35; 0,67], trend | +0,51 [0,25; 0,77], p = 0,0004, trend |
| LST NW Indie 2001–2024 | −0,72 [−1,10; −0,35], trend | −0,72 [−1,22; −0,22], p = 0,008, *kierunek stały, istotność zależy od okresu* (12 z 28 długich okien) |
| LST Europa Środkowa 2001–2024 | +0,88, p = 0,001, trend | +0,88, p = 0,034, *istotność zależy od okresu* (7 z 28) |
| LST Amazonia JJA | +0,58, p < 0,001 | +0,58 [0,16; 1,01], p = 0,013, trend |
| Wilgotność gleby NW Indie | p = 0,0004 | p = 0,026, trend |
| NDVI Europa Środkowa JJA | p = 0,066, brak trendu | p = 0,26, brak trendu |
| GISTEMP świat 1951–2025 | [0,149; 0,176], 13 756 komórek FDR | [0,132; 0,192], 12 602 komórek FDR |
| NDVI Amazonia, mapa | 2 461 z 6 000 komórek FDR | 611 z 6 000 |
| Laboratorium: 200 szeregów, 10 lat, φ = 0,7 | naiwny 83, skorygowany 14 | naiwny 83, skorygowany 5 |

Dryf Terra/Aqua (LST, °C/dekadę) nowymi testami: NW Indie Terra 2003–2021 −0,29 (p = 0,23), 2003–2024 −0,70 (p = 0,048); Aqua −0,38 (p = 0,16) i −0,52 (p = 0,019). Europa Środkowa Terra +1,10 (p = 0,08) i +0,90 (p = 0,07); Aqua +1,10 (p = 0,08) i +1,08 (p = 0,022). Amazonia we wszystkich czterech wariantach p ≤ 0,006. Wniosek: odporna jest tylko Amazonia. W NW Indiach i w Europie Środkowej (LST) kierunek się zgadza, ale istotność zależy od okresu i satelity.

**Wykonane 15.11 przez właściciela prezentacji:** slajdy przebudowano z nowego `evidence.json`: CI T2M [0,254; 0,766], 45 istotnych okien tego samego znaku i laboratorium 83/5. Usunięto stałe „Mann–Kendall agrees.”. Aktualny deck i PDF są teraz w osobnym, ignorowanym repo `earthatlas.github.io/`.

**Literatura:** Santer i in. (2000) JGR 105, 7337–7356 · Marriott i Pope (1954) Biometrika 41, 390–402 · Hirsch, Slack i Smith (1982) WRR 18, 107–121 · Hirsch i Slack (1984) WRR 20, 727–732 · Hamed i Rao (1998) J. Hydrol. 204, 182–196 · Berger (1982) Technometrics 24, 295–300 · Sen (1968) JASA 63, 1379–1389 · Benjamini i Hochberg (1995) JRSS-B 57, 289–300 · Wilks (2016) BAMS 97, 2263–2273. Kontekst: Noguchi, Gel i Duguay (2011) J. Hydrol. 410, 150–161 (bootstrap dla testów trendu; rozważany wariant, w naszych symulacjach nie poprawiał kalibracji względem metody analitycznej) · Collaud Coen i in. (2020) AMT 13, 6945–6964 (wpływ prewhiteningu i ziarnistości czasu na test MK).

## Walidacja danych (15.11)

**1. Maska jakości MODIS.** Podglądy COG na Planetary Computer mają *uśrednione* warstwy jakości (sprawdziliśmy: w podglądzie 4× `QC_Day` ma 223 różne wartości zamiast 8 kodów). Dlatego czytamy każdy kompozyt w **natywnej rozdzielczości** (NDVI 500 m, LST 1 km), tylko w oknie regionu, razem z warstwą jakości, i odrzucamy złe piksele **przed** uśrednianiem do 0,1°. Komórka wchodzi do kompozytu tylko wtedy, gdy co najmniej 20% jej pikseli przechodzi test. Kod: [atlas/sources/modis_pc.py](atlas/sources/modis_pc.py).
- NDVI (MOD13A1, *pixel reliability*): zostają 0 (dobre) i 1 (marginalne); odpadają 2 (śnieg/lód), 3 (chmury) i brak danych. Zostało 62–99% pikseli w poszczególnych latach (76–98% w całej kostce), najmniej w Amazonii i zimą w Europie.
- LST (MOD11A2/MYD11A2, `QC_Day`): zostaje kod 00 albo 01 z błędem LST ≤ 2 K; odpadają piksele niewyliczone. Zostało 98,5–99,9% (produkt LST jest już z definicji „bezchmurny”). Jeden obszar użytkownika leży nad otwartym morzem i nie ma LST ani przed, ani po masce.
- Reguły według podręczników MOD13 i MOD11 C6.1. Testy reguł bitowych są w [tests/test_stats.py](tests/test_stats.py).
- Przebudowano 18 kostek MODIS (regiony wbudowane i obszary użytkowników). Stare kostki: `data/cubes_backup_noqa_20261115/`. Odczyt jest szybki (ok. 5 s na rok i region), więc obliczenia na żądanie też używają maski.

**Przed i po masce** (cały okres, nowe testy statystyczne; trend na dekadę [95% CI], p, pokrycie komórek):

| Zmienna, region, sezon | Bez maski | Z maską | Werdykt bez → z |
| --- | --- | --- | --- |
| NDVI, Europa Środkowa, rok | +0,034 [0,015; 0,054], p = 0,001 | **+0,020** [0,012; 0,029], p < 0,001 | trend → trend |
| NDVI, Europa Środkowa, DJF | +0,071 [0,014; 0,122], pokrycie 95% | **+0,037** [0,015; 0,050], pokrycie 64% | trend → trend |
| NDVI, Amazonia, DJF (pora deszczowa) | +0,028 [0,008; 0,044], p = 0,006 | **+0,001** [−0,007; 0,007], p = 0,94 | istotność zależy od okresu → **brak trendu** |
| NDVI, Amazonia, JJA | −0,022 [−0,031; −0,013] | −0,022 [−0,031; −0,012] | trend → trend |
| NDVI, NW Indie, rok | +0,036 [0,028; 0,043] | +0,037 [0,029; 0,044] | trend → trend |
| LST Terra, Europa Środkowa, rok | +0,88 °C, p = 0,034 | +0,91 °C, p = 0,024 | bez zmian |
| LST Terra, NW Indie, rok | −0,72 °C, p = 0,008 | −0,68 °C, p = 0,007 | bez zmian |
| LST Terra, Amazonia, rok | +0,42 °C, p = 0,001 | +0,39 °C, p = 0,002 | bez zmian |

Wniosek: śnieg i chmury **podwajały** trend NDVI w Europie Środkowej (głównie zimą, jak podejrzewaliśmy) i tworzyły pozorny trend w porze deszczowej w Amazonii. Trendy LST prawie się nie zmieniły. Pełna tabela (27 wierszy) powstaje skryptem porównującym kopię zapasową z nowymi kostkami.

**2. Niezależny zapis opadów: GPCP v2.3.** Satelity mikrofalowe i podczerwone połączone z analizą deszczomierzy GPCC (NASA GSFC / University of Maryland; plik NOAA PSL, bez logowania, bez ograniczeń użycia). Siatka 2,5°, od **1988** (wcześniej tylko wskaźnik podczerwony OPI, mniej jednorodny). Adapter: [atlas/sources/gpcp.py](atlas/sources/gpcp.py). Kostki: świat + 3 regiony. Dla dowolnego obszaru używamy kostki światowej przyciętej do obszaru. GPCP jest *częściowo* niezależny od MERRA-2: nad Afryką MERRA-2 skaluje opad do klimatologii GPCP (Reichle i in. 2017), co zaznaczamy w zastrzeżeniach.

**3. Sprawdzenie niezależnym zbiorem przy każdym wyniku** ([atlas/api.py](atlas/api.py) `_cross_check`). Pary: T2M (MERRA-2) ↔ GISTEMP (stacje), opad MERRA-2 ↔ GPCP, LST Terra → Aqua. Liczymy ten sam test na wspólnym okresie, a o różnicy wielkości decyduje **trend szeregu różnic** obu zapisów z tymi samymi korektami pamięci (test różnicy trendów, Santer i in. 2000). Kategorie: zgodne, ten sam kierunek i różna wielkość, istotny tylko jeden, żaden nie jest istotny, sprzeczne, niejasne. Wynik trafia do odpowiedzi, karty wyniku i nowej sekcji **Validation** w zakładce Methods (`/api/validation`).

| Region | Wynik | Niezależne sprawdzenie | Wniosek |
| --- | --- | --- | --- |
| Europa Środkowa | T2M +0,51 °C/dek. | GISTEMP +0,51 | zgodne (p różnicy = 0,99) |
| Amazonia | T2M +0,50 | GISTEMP +0,27 | ten sam kierunek, różna wielkość |
| NW Indie | T2M −0,05 (n.i.) | GISTEMP +0,25 (istotny) | **sprzeczne** – reanaliza vs stacje |
| Amazonia | opad MERRA-2 −0,71 mm/d/dek. | GPCP −0,32 | ten sam kierunek, oba istotne, różnica nieistotna (p = 0,06) |
| NW Indie | opad MERRA-2 +0,20 | GPCP +0,09 (n.i.) | istotny tylko jeden, wielkości różne |
| NW Indie | LST Terra −0,70 | Aqua −0,52 | zgodne |

Dzięki temu przypadek „opad MERRA-2 w Amazonii do weryfikacji” jest rozstrzygnięty: kierunek potwierdza niezależny zapis, a wielkość z MERRA-2 jest prawdopodobnie zawyżona. Rozbieżność T2M w NW Indiach aplikacja pokazuje wprost, zamiast ją ukrywać.

## Czego jeszcze potrzebujemy (propozycja kolejności)

1. **Przegląd kodu przez zespół.**
2. **Live demo (konieczne do zgłoszenia):** publiczny URL bez logowania, najlepiej przed 15.11 rano. To jeden proces uvicorn + statyczne pliki + ok. 60 MB kostek; `data/raw` nie jest potrzebne. Do ustalenia: gdzie hostujemy (VM, kontener, tunel z tego serwera) i czy publiczne demo ma pozwalać na obliczenia na żądanie. Rekomenduję limit kolejki i rozmiaru; na razie zadania nie mają limitu liczby ani czasu.
3. **Materiały zgłoszenia:** film ≤ 30 s (glob → zaznaczenie Amazonii → wynik → macierz) albo ≤ 7 slajdów po angielsku, opis projektu, lista źródeł i licencji.
4. **Earthdata Login** (`~/.netrc`), potem adapter IMERG monthly. Zastąpi wątpliwy opad MERRA-2 w Amazonii i da zmienną zgodną z planem P0.
5. QA dla MODIS (`pixel_reliability` / `QC_Day`).
6. P1: GRACE (magazyn wody) dla NW Indii, czyli dokładnie kontrast „zieleń vs woda”. Ewentualnie zlewnie HydroBASINS zamiast prostokątów.
7. Drobne: obszary przez linię zmiany daty, tłumaczenie UI, dostępność, test na telefonie.

## Wygląd i ikony (14.11 wieczorem)

- Logo w nagłówku jest pisane fontem **Nasalization** (Ray Larabie, freeware 1997; plik `web/fonts/nasalization.ttf`, skopiowany z załącznika Mai). Wzdłuż krawędzi liter pojawia się jedna iskierka naraz, w losowym miejscu. Przy włączonym w systemie ograniczeniu animacji (`prefers-reduced-motion`) iskierka jest wyłączona.
- Ikony są w jednym pliku `web/icons.svg` (sprite z elementami `<symbol id="i-…">`). Ikony dostarczył zespół. Żeby podmienić ikonę, wklej nowy SVG do środka `<symbol>` i zostaw jego `id`. Kolor ikony bierze się z `currentColor`.
- Favicon globu z książką to własny SVG projektu. Skale barw miesięcznych warstw Globe pochodzą z [NASA EOSDIS GIBS](https://gibs.earthdata.nasa.gov/legends/) i są osadzone jako oficjalne obrazy PNG z oznaczeniem „NASA GIBS”.
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
  - pewność wyniku: ile innych okresów daje ten sam kierunek, ile z nich jest też istotnych i czy test rangowy (Mann–Kendall z korektą pamięci danych) daje ten sam wynik,
  - jedno najważniejsze zastrzeżenie do źródła danych,
  - rozwijane „How we know” z liczbami.
- Pytanie o drugiego satelitę (Aqua) porównuje wynik z Terrą dla tego samego obszaru i okresu.
- Pytanie „Where is it warming fastest?” wskazuje komórkę z najszybszym istotnym ociepleniem.
- **Bez modelu językowego:** odpowiedzi to stałe szablony w `atlas/answers.py` wypełniane liczbami z analizy. Odpowiedź trafia też do eksportu JSON (`answer`) i ma testy w `tests/test_answers.py`. Nie podaje przyczyn zmian.

## Publiczne demo (Tailscale Funnel)

- Adres: **https://earth-atlas.tail969737.ts.net**. Funnel na osobnym węźle `earth-atlas` (osobny `tailscaled` w `~/.local/state/tailscale-earth/`) przekazuje ruch tylko do `127.0.0.1:8780`. Węzeł `kmiwz`, SSH, port 8765 i reszta tailnetu nie są wystawione.
- Na 8780 działa instancja w trybie publicznym (`ATLAS_PUBLIC=1`):
  - bez `/docs`, `/redoc` i `/openapi.json`,
  - limity liczenia nowych obszarów: 3 zadania naraz, 1 na odwiedzającego, 8 na godzinę,
  - sprzątanie obszarów użytkowników (7 dni, maks. 60).
- Po restarcie serwera trzeba ręcznie uruchomić oba procesy (konfiguracja Funnel zostaje zapisana w stanie węzła):

```bash
cd /storage/home/moai/nasaapps && ATLAS_PUBLIC=1 ATLAS_PRUNE_DAYS=7 ATLAS_MAX_CUSTOM=60 setsid nohup .venv/bin/uvicorn atlas.api:app --host 127.0.0.1 --port 8780 --proxy-headers > data/public.log 2>&1 < /dev/null &
```

```bash
D=~/.local/state/tailscale-earth; setsid nohup ~/.local/bin/tailscaled --tun=userspace-networking --port=0 --statedir=$D --socket=$D/tailscaled.sock > $D/tailscaled.log 2>&1 < /dev/null &
```

- Wyłączenie demo: `~/.local/bin/tailscale --socket=$HOME/.local/state/tailscale-earth/tailscaled.sock funnel --https=443 off`.
- Zmiany w kodzie Pythona dochodzą do demo dopiero po restarcie procesu na 8780.
