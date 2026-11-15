# Earth Evidence Atlas – prezentacja PollubAI

Otwórz `earth-evidence-atlas.html` w przeglądarce. To samodzielny plik: font, ilustracje, wykresy, style, skrypty i zapis wyników są osadzone wewnątrz. Slajdy działają bez internetu; link do aktualnego demo wymaga połączenia.

`earth-evidence-atlas.pdf` zawiera dokładnie **7 slajdów po angielsku**, łącznie z okładką. To wersja przeznaczona do oficjalnego zgłoszenia; HTML z polskimi notatkami służy także do przygotowania wystąpienia. Limit i język przyjęto z dostarczonych lokalnych kopii Project Submission Guide i Judging & Awards Guide. Aktualizacja z 15.11 sprawdza stan projektu względem świeżych odpowiedzi API i bieżącego interfejsu; nie jest ponownym audytem regulaminu.

## Obsługa

- Strzałki, spacja, Home/End – zmiana slajdu.
- **F** – pełny ekran.
- **N / Notes · PL** – polskie notatki do aktualnego slajdu, z proponowanym scenariuszem około 3 minut. Czas nie jest oficjalnym limitem wystąpienia.
- **D / Details & sources** – pełna zgodność z zadaniem, opcjonalne sugestie, inwentarz funkcji, źródła i ograniczenia, wyniki oraz ścieżka demonstracji.
- **Reading view** – wszystkie slajdy, z układem do czytania na telefonie.
- Na slajdzie 4 przyciski przełączają trzy zapisane przykłady: pamięć szeregu, punkty odstające i wybór sezonu. Druk przywraca przykład z pamięcią szeregu.
- Na slajdzie 7 kliknij ramki **Add photo**, aby dodać trzy zdjęcia zespołu. Imiona i role edytujesz kliknięciem. **Save with photos** pobiera samodzielny HTML ze zdjęciami i podpisami; otwórz pobrany plik, aby korzystać z zapisanej wersji. Po zmianach możesz też ponownie wydrukować PDF.
- **Print / PDF** – druk siedmiu slajdów. Panele szczegółowe i notatki nie dodają stron do PDF.

## Import do Canvy

**Uwaga: pliki `earth-evidence-atlas-canva-*` są eksportami starszej wersji i nie obejmują aktualizacji naukowej, nowych funkcji ani potwierdzonych podpisów zespołu. Bieżąca prezentacja to `earth-evidence-atlas.html` i `earth-evidence-atlas.pdf`.** Historyczne eksporty zachowano, aby nie usuwać materiałów zespołu. Poniższy opis dotyczy wyłącznie tych starszych plików. Plik `earth-evidence-atlas-canva-editable.pdf` jest kopią poprawionego PDF. Oba formaty mają siedem slajdów i osobne teksty, kształty oraz obrazy; zrzuty interfejsu pozostają pojedynczymi obrazami. Ziemia jest osobnym, nieprzezroczystym obrazem RGB. Eksport PDF 1.3 używa prostych kolorów DeviceRGB, osadzonych fontów i ścieżek wektorowych, bez masek, profili ICC, gradientów, grup przezroczystości i stanów ExtGState. Subtelne gradienty tła zastąpiono jednolitymi wypełnieniami. W PPTX zastosowano Arial, również w nazwie aplikacji, aby ograniczyć podmianę fontów.

Sprawdzono lokalny wygląd wszystkich stron PDF, zachowanie liter i cyfr ze źródła oraz otwarcie i eksport PPTX w LibreOffice. `canva-validation.json` zawiera wyniki i skróty plików. Importu w samej Canvie nie przetestowano; lokalny test nie potwierdza zachowania jej importera. Aktualny HTML i PDF zostały odświeżone osobno; historyczna walidacja importu nie dotyczy nowych plików.

## Co zawiera materiał

1. Problem i obietnica produktu.
2. Wszystkie cztery obowiązkowe cele wyzwania.
3. Rzeczywisty wynik NASA POWER/MERRA-2 dla Europy Środkowej z niepewnością i sprawdzeniem innych okresów.
4. Laboratorium fałszywych alarmów, wpływ dwóch punktów odstających oraz pomocniczy, jawnie eksploracyjny przykład MODIS.
5. Osiem serii danych z MODIS, POWER/MERRA-2, GPCP i GISTEMP. Serie POWER mają wspólne pochodzenie; osiem serii nie oznacza ośmiu niezależnych źródeł.
6. Działające funkcje: glob, pobieranie obszarów, porównania źródeł, wyszukiwanie podobnych trendów GISTEMP, Resilience dla infrastruktury cywilnej i obronnej, eksport, języki i widoki mobilne.
7. Metoda i zespół, alfabetycznie według nazwisk: Maks Kozieł – Platform & Reliability Lead; Jan Kwapiński – Science & Data Lead; Maja Sykuła – Product & Experience Lead. Zdjęcia można dodać w HTML. Role i wkład przypisano zgodnie z informacją zespołu; kolejne kroki to badania użyteczności, dostępności i wolnej zmienności klimatu.

Rozwijany panel zawiera także pełny dostarczony tekst zadania. Wskazuje, które sugestie są opcjonalne i które produkty oraz funkcje nie są obecnie zaimplementowane. Nie przedstawia planów jako gotowych możliwości.

## Liczby, obrazy i odtwarzalność

- `evidence.json` to zapis 13 rzeczywistych odpowiedzi analiz, tabeli walidacyjnej, karty Resilience oraz jawnie syntetycznych eksperymentów. Zawiera parametry, pochodzenie danych, metody, datę, wersję Git i skróty plików źródłowych. Ten sam zapis można pobrać z HTML.
- Główny przykład: `t2m`, `central_europe`, 1981–2025, wszystkie miesiące. Wynik: +0,509551 °C/dekadę, CI 95% [0,254052; 0,765551]. Kierunek zgodny w 133 ze 136 badanych okien, z czego 45 okien ma ten kierunek i p < 0,05. Okna się nakładają i nie są niezależnymi powtórzeniami. Porównanie GISTEMP dla tych samych lat: +0,509067 °C/dekadę.
- Symulacja: 200 prób, 10 lat, φ = 0,7, seed = 1000. Alarmy: 83 bez korekty, 5 po aktualnych sprawdzianach pamięci miesięcznej i rocznej (41,5% i 2,5%). Słupki błędów to przedziały Wilsona 95%, a szary słupek 5% jest poziomem odniesienia. To nie są obserwacje Ziemi.
- Najnowsze ćwiczenie z dwoma punktami odstającymi ma osobny zapis w `simulation_spikes`, z datą i skrótem pliku frontendu. Parametry odpowiadają obecnemu domyślnemu ćwiczeniu: 5 lat, seed 15, φ = 0,25, σ = 0,35. Funkcja `addSpikes()` jest wykonywana z aktualnego pliku aplikacji; wynik jest porównywany z interfejsem podczas przechwytywania. Starsze ćwiczenie skoku średniej nie jest częścią obecnego zapisu dowodów.
- Zrzuty w `assets/` pochodzą z rzeczywistej aplikacji. Wektorowe wykresy są eksportami Plotly utworzonymi z tych samych odpowiedzi API. Nie są makietami wyników.
- MODIS korzysta z natywnej rozdzielczości i maskowania jakości przed agregacją. NDVI zachowuje piksele dobre i marginalne. Panel źródeł opisuje reguły QA, dryf orbit, przybliżone miesiące, ograniczenia reanaliz i rozdzielczości oraz brak wnioskowania przyczynowego. Porównanie opadu z GPCP jest dostępne, ale zgodność nie ustala przyczyn ani pełnej niezależności danych.
- Obrazy NASA GIBS, analiza GISTEMP, granice Natural Earth, gwiazdy Yale BSC/d3-celestial, font Ray Larabie z 1997 r. (wewnętrzna rodzina „Nasa”, alias CSS „Nasalization”) i ikony pochodzą z zasobów istniejącej aplikacji. Źródła i licencje są również wymienione w HTML i głównym README projektu. Plotly: MIT; Natural Earth: public domain; d3-celestial: BSD-3-Clause; Font: metadane „Freeware by Ray Larabie 1997”.
- Publiczny adres demo został otwarty bez konta; Resilience załadowało cztery karty przez zgodnościowy mechanizm starszego API. `deployment-check.json` zapisuje wynik kontroli; samo `/api/resilience` zwracało wtedy 404, więc sprawdzono również rzeczywisty widok w przeglądarce. Dostępność może się zmienić; HTML i PDF zachowują zapisane ilustracje offline.

## Edycja

Edytuj `deck.template.html`, a następnie uruchom z dowolnego katalogu:

```bash
python3 /storage/home/moai/nasaapps/presentation/build.py
```

Skrypt budujący HTML używa biblioteki standardowej Pythona, `evidence.json`, `deployment-check.json`, lokalnych `assets/`, fontu i sprite’u ikon. Zmiana metod lub danych wymaga ponownego przechwycenia wyników i figur; nie należy ręcznie podmieniać liczb w slajdach.

Pełny proces odświeżenia, po uruchomieniu świeżej własnej instancji API na wolnym porcie (przykład: 8776):

```bash
.venv/bin/python presentation/capture.py --base-url http://127.0.0.1:8776
.venv/bin/python presentation/render_assets.py --base-url http://127.0.0.1:8776
.venv/bin/python presentation/build.py
.venv/bin/python presentation/verify.py
```

`capture.py` wykonuje tylko odczyty API, bez pobrań i przebudowy kostek. Sprawdza, czy źródła nie zmieniły się podczas zapisu. `render_assets.py` korzysta z lokalnego Chrome, istniejącego Playwright i Plotly z repo; tworzy figury z zapisu oraz zrzuty aplikacji. `verify.py` wymaga także Pillow, `pdfinfo` i `pdftotext`; sprawdza powiązanie figur z danymi, zgodność źródeł, siedem slajdów i stron PDF, brak kolizji ze stopką, działanie offline, pobieranie dowodów, trzy przykłady, zdjęcia zespołu i zapis HTML oraz widok 390 px. Wyniki zapisuje w `validation.json`, a podgląd w `preview.png`. Kontrolę publicznego demo należy odświeżyć osobno, gdy zmienia się jego wdrożenie.

Prezentacja nie została automatycznie opublikowana ani wysłana do organizatorów. Link do prezentacji/demo i link do końcowego projektu należy podać osobno zgodnie z formularzem zgłoszenia.
