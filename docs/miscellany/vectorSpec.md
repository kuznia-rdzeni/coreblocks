Najważniejsze elementy:
- 7 CSR-ów
- 32 rejestry
- zmiany w mstatus/sstatus/vsstatus - pozwala wyłączyć jednostkę wektorową
- definicje zachowania dla elementów zamaskowanych i z ogona wektora
- zamaskowane elementy nigdy nie generują wyjątków
- do wyliczeń maska jest zawsze brana z rejestru v0
- standard dopuszcza nieprecyzyjne wyjątki, ale ich nie wspiera, więc jeśli chce się powiedzieć, że jest się zgodny z
  rozszerzeniem V to trzeba mieć precyzyjne wyjątki
- rozszerzenie V wymaga rozszerzeń F i D
- VL może być rozbijany na różne sposoby, by zapewnić optymalne wykorzystanie lane-ów


Calling convention (draft):
- wszystkie rejestry wektorowe są caller-save
- syscalle invalidują wszystkie rejestry wektorowe
