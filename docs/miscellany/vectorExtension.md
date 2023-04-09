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


Ara: A 1 GHz+ Scalable and Energy-Efficient RISC-V Vector Processor with Multi-Precision Floating Point Support in 22 nm FD-SOI:
- procesor in-order, rozszerzenie V in-order
- na podstawie wersji 0.5 specyfikacji rozszerzenia V
- brak forwardingu
- w rozszerzeniu V jest instrukcja, która czyta 4 rejestry i zapisuje w wyniku jeden rejestr
- każdy fragment VRF jest złożony z 8 banków o jednym porcie do odczytu i jednym do zapisu
- ciekawy pomysł: dostępy do banków mają piorytety - wyższy z jednostek wykonujących częste/regularne dostępy, niższy z
  pozostały (bowiem skoro rzadziej potrzebują rejestrów, to nic im się nie stanie jeśli trochę poczekają)
- wartości skalarne w rejestrach wektorowych są przechowywane tylko w jednej kopii, a następnie wirtualnie kopiowane do
  wszystkich pól wektora
- zauważają, że dostępy do MUL i FPU raczej nie będą się odbywać w tym samym czasie, więc można zrobić trochę
  optymalizacji
- ważne: wbrew pozorom wydajność dla krótkich wektorów też ma znaczenie, bowiem macierz może być duża, ale pod względem
  wymiarowości, a pojedyncze wektory mogą być krótkie np. 3 x 112 x 112 (sieć neuronowa LeNet)
- problemy ze skalowalnością wraz ze wzrostem liczby lane (rdzeń o 16 lane miał o 1/5 gorsze zegary 1,25GHz vs 1GHz)


Hawacha:
- niezgodna ze standardem RISC-V V (choć dosyć zbliżona)
- całkowicie oddzielny rdzeń, który ma własny fetch unit
- każdy lane ma osobny port do dostępu do pamięci
- vector runachead unit (?)
- ~90 MHz na FPGA
- Chisel3


VEGAS: Soft Vector Processor with Scratchpad Memory
- procesor wektorowy na FPGA
- architektura niezgodna z RISC-V V (nawet tego rozszerzenia nie było wtedy w planach)
- nie ma load-ów/stor-ów więc nie ma problemu z opóźnieniami związanymi z pamięcią
- całe dane przechowywane w scratchpadzie FPGA, który robi za dynamiczny VRF
- rejestr, to wskaźnik z adresem na początek wektora w pamięci scratchpad
- programista ręcznie zarządza pobieraniem danych z RAM, poprzez ręczne zarządzanie DMA
- używa makr w C aby wygenerować kod asemblerowy na ten procesor wektorowy - kompilator nie ma wsparcia
- Obserwacja: SIMD - zdefiniowany stały rozmiar bloku/wektora, procesory wektorowe mają długoś wektora ustalaną w
  runtimie
- wspiera przetwarzanie 32 bitów w jednym cyklu przez jedno ALU, bity te to może być jedno słowo, dwa półsłowa, lub
  cztery bajty
- działa na FPGA z maksymalnym zegarem 130 MHz (sama część wektorowa)
- ich procesor działa szybko bo nie ma load/store -> znane ograniczenie, procesor działa wolno jak dane nie mieszczą się
  w scratchpadzie
- dzięki temu, że rejestry to wskaźniki, poza 8 rejestrami architektonicznymi mogą mieć wiele więcej rejestrów
  przechowywanych w pamięci NIOS-II jako wartości skalarne
- jeden rejestr zarezerwowany na kopie w celu wyrównania dostępów do pamięci
- Ważne: używają sieci Benes-a jako crossbarów by zejść z O(N^2) do O(N log N) ze złożonością sieci przełączników
- Twierdzą, że są lepsi od procesorów Intela - ale swój kod mają ręcznie optymalizowany w asemblerze, a kod na procesor
  Intela nie używa nawet SSE :D











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

- jak zrobić dobre ALU/ jednostkę mnożącą, by na raz wspierała operacje na wielu długościach?
- jak zrobić dobrze sieć przełączników?


Sieci przełączników:
- Sieci banyan - sieci w których istnieje dokładnie jedna droga z dowolnego źródła do dowolnego celu
- Sieć delta - sieć banyan w której pakiety są samo-routowalne
- Sieć omega - łatwe adresowanie i routowanie pakietów (pierwsza sieć banyan demonstrująca samo-routowalnośc)
- Sieć butterfly - jest ładnie rekurencyjna, więc relatywnie łatwo da radę udowodnić load-balancing

Rozważmy jeden przełącznik w sieci przełączników. Czy to, że może on przesłać maksymalnie jedno wejście na jedno wyjście
ma istotny wpływ na złożoność takiego przełącznika w porównaniu do sytuacji w której jeśli oba wejścia są włączone, to
wysyła je na oba wyjścia?
