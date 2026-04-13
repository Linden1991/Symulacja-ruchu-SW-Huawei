# Symulacja-ruchu-SW-Huawei

Skrypt do automatyzacji testowania łączności na urządzeniach sieciowych CPE (Huawei / Cisco) 
poprzez tymczasową rekonfigurację switcha i wykonanie testu ping.

## Opis

Narzędzie łączy się przez SSH do routera CPE, następnie wykonuje połączenie 
do docelowego switcha (stelnet dla Huawei, SSH dla Cisco), tymczasowo modyfikuje 
konfigurację interfejsu VLAN i trasy domyślnej, przeprowadza test ping, 
a następnie automatycznie przywraca pierwotną konfigurację.

## Funkcje

- Obsługa CPE Huawei i Cisco
- Automatyczna obsługa promptów SSH (klucze, zmiana hasła)
- Weryfikacja hostname przed każdą krytyczną operacją
- Potwierdzenie użytkownika przed wprowadzeniem zmian
- Tryb debug z podglądem surowego outputu
- Automatyczne przywracanie konfiguracji po teście

## Wymagania

- Python 3.x
- paramiko (`pip install paramiko`)

## Użycie

python Symulacja_DATA_v6.py

Skrypt interaktywnie pyta o:
- IP urządzenia CPE
- Login i hasło RADIUS
- Ostatni oktet IP switcha
- Numer VLAN do testu

## Uwagi

Skrypt używa `paramiko.AutoAddPolicy()` — klucze SSH są akceptowane automatycznie.
Jest to celowe zachowanie dla środowiska laboratoryjnego/testowego.

---
*Kod rozwijany przy pomocy AI, Claude (Anthropic)*
