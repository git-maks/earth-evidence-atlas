# Earth Evidence Atlas – prezentacja PollubAI

Otwórz `earth-evidence-atlas.html` w przeglądarce. To samodzielny plik: font, ilustracje, wykresy, style, skrypty i zapis wyników są osadzone wewnątrz. Slajdy działają bez internetu; link do aktualnego demo wymaga połączenia.

`earth-evidence-atlas.pdf` zawiera dokładnie **7 slajdów po angielsku**, łącznie z okładką. To wersja przeznaczona do oficjalnego zgłoszenia; HTML z polskimi notatkami służy także do przygotowania wystąpienia. Limit i język przyjęto z dostarczonych lokalnych kopii Project Submission Guide i Judging & Awards Guide. Próba ponownego odczytu oficjalnych stron podczas przygotowania zakończyła się błędami sieci; nie przedstawiamy jej jako nowej weryfikacji regulaminu.

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

Do importu użyj `earth-evidence-atlas-canva-fixed.pdf` albo `earth-evidence-atlas-canva-editable.pptx`. Plik `earth-evidence-atlas-canva-editable.pdf` jest kopią poprawionego PDF. Oba formaty mają siedem slajdów i osobne teksty, kształty oraz obrazy; zrzuty interfejsu pozostają pojedynczymi obrazami. Ziemia jest osobnym, nieprzezroczystym obrazem RGB. Eksport PDF 1.3 używa prostych kolorów DeviceRGB, osadzonych fontów i ścieżek wektorowych, bez masek, profili ICC, gradientów, grup przezroczystości i stanów ExtGState. Subtelne gradienty tła zastąpiono jednolitymi wypełnieniami. W PPTX zastosowano Arial, również w nazwie aplikacji, aby ograniczyć podmianę fontów.

Sprawdzono lokalny wygląd wszystkich stron PDF, zachowanie liter i cyfr ze źródła oraz otwarcie i eksport PPTX w LibreOffice. `canva-validation.json` zawiera wyniki i skróty plików. Importu w samej Canvie nie przetestowano; lokalny test nie potwierdza zachowania jej importera. Oryginalny HTML i PDF zgłoszeniowy pozostają bez zmian.

## Co zawiera materiał

1. Problem i obietnica produktu.
2. Wszystkie cztery obowiązkowe cele wyzwania.
3. Rzeczywisty wynik NASA POWER/MERRA-2 dla Europy Środkowej z niepewnością i sprawdzeniem innych okresów.
4. Laboratorium fałszywych alarmów, wpływ dwóch punktów odstających oraz pomocniczy, jawnie eksploracyjny przykład MODIS.
5. Siedem zbiorów NASA i ich pochodzenie.
6. Dodatkowe działające funkcje: glob, obrazy historyczne, pobieranie obszarów na żądanie, porównania, eksport, zapis miejsc, języki i widoki mobilne.
7. Trzy zasady wiarygodnej analizy trendu, miejsca na zdjęcia i podpisy trzech osób z zespołu oraz kolejne kroki walidacji. Adres prototypu pozostaje w stopce.

Rozwijany panel zawiera także pełny dostarczony tekst zadania. Wskazuje, które sugestie są opcjonalne i które produkty oraz funkcje nie są obecnie zaimplementowane. Nie przedstawia planów jako gotowych możliwości.

## Liczby, obrazy i odtwarzalność

- `evidence.json` to zapis 12 rzeczywistych odpowiedzi analiz oraz jawnie syntetycznych eksperymentów. Zawiera parametry, pochodzenie danych, metody, datę, wersję Git i skróty plików źródłowych. Ten sam zapis można pobrać z HTML.
- Główny przykład: `t2m`, `central_europe`, 1981–2025, wszystkie miesiące. Wynik: +0,509551 °C/dekadę, CI 95% [0,352253; 0,66685]. Kierunek zgodny w 133 ze 136 badanych okien, z czego 81 okien ma ten kierunek i p < 0,05.
- Symulacja: 200 prób, 10 lat, φ = 0,7, seed = 1000. Alarmy: 83 bez korekty, 14 po korekcie. Słupki błędów to przedziały Wilsona 95%, a szary słupek 5% jest poziomem odniesienia. To nie są obserwacje Ziemi.
- Najnowsze ćwiczenie z dwoma punktami odstającymi ma osobny zapis w `simulation_spikes`, z datą i skrótem pliku frontendu. Starszy `simulation_step` pozostaje wyłącznie archiwalnym payloadem; nie jest przedstawiany jako aktualna funkcja interfejsu.
- Zrzuty w `assets/` pochodzą z rzeczywistej aplikacji. Wektorowe wykresy są eksportami Plotly utworzonymi z tych samych odpowiedzi API. Nie są makietami wyników.
- MODIS bez pixel QA, dryf satelitów, ograniczenia reanaliz i brak wnioskowania przyczynowego są opisane w panelu źródeł. Sygnał opadu w Amazonii nie jest prezentowany jako potwierdzone odkrycie.
- Obrazy NASA GIBS, analiza GISTEMP, granice Natural Earth, gwiazdy Yale BSC/d3-celestial, font Nasalization i ikony pochodzą z zasobów istniejącej aplikacji. Źródła i licencje są również wymienione w HTML i głównym README projektu. Plotly: MIT; Natural Earth: public domain; d3-celestial: BSD-3-Clause; Nasalization: freeware 1997, Ray Larabie.
- Publiczny adres demo został otwarty bez konta w oddzielnym kontekście przeglądarki podczas zapisu materiałów. Dostępność może się zmienić; HTML i PDF zachowują zapisane ilustracje offline.

## Edycja

Edytuj `deck.template.html`, a następnie uruchom z dowolnego katalogu:

```bash
python3 /storage/home/moai/nasaapps/presentation/build.py
```

Skrypt używa biblioteki standardowej Pythona, `evidence.json`, lokalnych `assets/` i istniejącego fontu oraz sprite’u ikon projektu. Po przebudowie otwórz HTML i ponownie wygeneruj PDF. Zmiana opisu nie zastępuje ponownego pobrania i sprawdzenia danych, jeżeli mają zmienić się wyniki.

Prezentacja nie została automatycznie opublikowana ani wysłana do organizatorów. Link do prezentacji/demo i link do końcowego projektu należy podać osobno zgodnie z formularzem zgłoszenia.
