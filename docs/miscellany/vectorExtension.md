RISC-V2: A Scalable RISC-V Vector Processor
- rozdzielają instrukcje na dwie ścieżki (skalarną i wektorową)
- nowości:
    - wprowadzają renaming rejestrów wektorowych
    - dynamiczna redukcja drzew
    - decoupled execution scheme
2 way out-of-order superscalar processor
- scorboarding (dopóki wszystkie argumenty nie są gotowe, doputy instrukcja wektorowa jest stallowana -> możliwe
  problemy z niepotrzebnym oczekiwaniem w momencie jak można już zacząć przetwarzać początek wektora
- instrukcja wektorowa rozbijana na uops i każda uops jest przetwarzana niezależnie
- każda uops operuje na przydzielonym zakresie rejestrów -> czy to oznacza, że rejestr jednego wektora składa się z
  wielu mniejszych rejestrów?
- dzięki rozbiciu instrukcji wektorowej na uops mogą wprowadzić bankowanie pliku rejestrów wektorowych
- część wektorowa jest in-order
- co z przerwaniami?
- mówią dużo o loop unrolling ale to nie ma sensu... Nie wskazują żadnych pętli, tylko to, że można łączyć rejestry
- rozdzielili wektorowe operacje na pamięci od operacji erytmetycznych - operacja na pamięci idzie do bloku zarządzania
  pamięcią, gdzie jest następnie przetwarzana, natomiast operacja duch blokuje scorboard w części arytmetycznej
- rozważają redukcje w sensie arytmetycznym - wiele argumentów -> jeden wynik
- SystemVerilog na Githubie - projekt martwy w dniu publikacji :D
- służy jako demonstracja do artykułu, nic więcej się z nim nie zadziało
- wspierają maksymalnie 16 lane (gdzieś w kodzie są jakieś hardcody :D)
- rozszerzenie V in-order


A “New Ara” for Vector Computing: An Open Source Highly Efficient RISC-V V 1.0 Vector Processor Design:
- ładne porównanie implementacji rozszerzeń wektorowych
- historia zmian w specyfikacji V
- dobre wprowadzenie do rozszerzenia V
- objaśnia czemu banki rejestrów są powiązane z lane - by sieć połączeń skalowała się liniowo a nie kwadratowo
- aby dobrze wykorzysać data pararelism - kolejne elementy rejestru wektorowego powinny być zmapowane na kolejne lane
  (tak przynajmniej twierdzą, nie wiem czy ma to zastosowanie do coreblocksa)
    - w zależności od tego jakiego dane trzymamy w takim podejściu, to jeden bajt może być zmapowany na różne lane
- Issue rate 1 instrukcja na 4 cykle
- procesor in-order z rozszerzeniem V in-order
- wołają jednostkę vektorową, po issue stage (instrukcja wktorowa przechodzi przez renaming skalarny itp)
- zwracają uwagę na to, że trzeba utrzymywać memory-cocherency - zapis z wektora musi unieważniać cache skalarny, zapis
  skalarny musi być widoczny podczas odczytu wektorowego
- brak spekulacji
- tail undisturbed policy - niezmieniane elementy na końcu wektora w rejestrze do którego zapisujemy, powinny pozostać
  poprawne po zapisaniu do tego rejestru nowych danych, jeśli nowe dane mają inny rozmiar pojedynczego elementu powoduje
  to koniecznosc przepisania starych elementów
- bardzo dobry pomysł: w przypadku jeśli robić się renaming rejestrów wektorowych, to dobierać je tak, by dane, które
  znajdowały się w rejestrze poprzednio miały taką samą długość pojedyńczego elementu



- porównanie dwóch typów chainowania instrukcji (coś w stylu starych vs nowych łącz telefonicznych)
    - z rezerwacją sprzętu
    - dynamiczny (bez rezerwacji)
- piorytety starszych instrukcji z siecią do rozgłaszania przekręcenia licznika

- schedulery:
    - brak chainingu - zapis zawsze do rejestru
    - chaining z jednym cyklem opóźnienia - czekamy na następną instrukcję anim wyślemy aktualną, jeśli można zchainować
      to to robimy, jeśli nie to puszczamy bez chainingu
    - chaining z możliwością zrównolegalania obliczeń w ramach jednego wektora

- chaining pozwala nie alokować rejestru pośredniego (?)

- rozszerzenie V pozwala powiedzieć procesorowi ile aktualnie chcemy mieć logicznych rejestrów wektorowych (?)
