import paramiko
import time
import getpass
import re

# KONFIGURACJA

TRYB_DEBUG = False
TIMEOUT_POLACZENIA = 30
TIMEOUT_KOMENDY = 10

# PROMPTY I WZORCE

OBSLUGA_PROMPTOW = {
    r'Change now\?\s*\[Y/N\]:?\s*$': 'N',
    r'The password needs to be changed.*\[Y/N\]:?\s*$': 'N',
    r'Continue to access it\?\s*\[Y/N\]:?\s*$': 'Y',
    r"Save the server's public key\?\s*\[Y/N\]:?\s*$": 'Y',
    r'The server is not authenticated.*\[Y/N\]:?\s*$': 'Y',
    r'Are you sure to continue\?\s*\[Y/N\]:?\s*$': 'Y',
    r"Please choose 'YES' or 'NO'.*\[Y/N\]:?\s*$": 'Y',
}

WZORCE_GOTOWOSCI = [
    r'<[\w\-]+>',
    r'\[[\w\-~]+\]',
    r'[\w\-]+[#>]\s*$',
]

# FUNKCJE POMOCNICZE

def debug_print(msg):
    if TRYB_DEBUG:
        print(f"[DEBUG] {msg}")


def wyciagnij_hostname_z_promptu(output):
    match = re.search(r'[<\[]~?([\w\-]+)[>\]]\s*$', output)
    if match:
        return match.group(1)
    return None


def czy_tryb_system_view(output):
    """Sprawdza czy jestesmy w trybie system-view [hostname] (uprzywilejowany)."""
    if re.search(r'\[~?[\w\-]+\]\s*$', output):
        return True
    return False


def czy_tryb_uzytkownika(output):
    """Sprawdza czy jestesmy w trybie uzytkownika <hostname>."""
    if re.search(r'<[\w\-]+>\s*$', output):
        return True
    return False


def potwierdz_operacje(komunikat):
    print(f"\n{'='*60}")
    print(f"[UWAGA] {komunikat}")
    print(f"{'='*60}")
    odpowiedz = input("Czy kontynuowac? (tak/nie): ").strip().lower()
    return odpowiedz in ['tak', 't', 'yes', 'y']


def wyswietl_status(komunikat, typ="info"):
    prefiksy = {
        "info": "[INFO]",
        "ok": "[OK]",
        "blad": "[BLAD]",
        "uwaga": "[UWAGA]",
    }
    prefiks = prefiksy.get(typ, "[INFO]")
    print(f"{prefiks} {komunikat}")


def czytaj_do_promptu(shell, timeout=10, dodatkowe_oczekiwanie=0.5):
    output = ""
    czas_startu = time.time()
    
    while True:
        if time.time() - czas_startu > timeout:
            break
        
        if shell.recv_ready():
            fragment = shell.recv(4096).decode('utf-8', errors='ignore')
            output += fragment
            debug_print(f"Otrzymano: {repr(fragment)}")
            
            prompt_obsluzony = False
            for wzorzec, odpowiedz in OBSLUGA_PROMPTOW.items():
                if re.search(wzorzec, output, re.IGNORECASE | re.DOTALL):
                    debug_print(f"Wykryto prompt Y/N, wysylam: {odpowiedz}")
                    shell.send(f"{odpowiedz}\n")
                    time.sleep(0.5)
                    prompt_obsluzony = True
                    break
            
            if prompt_obsluzony:
                continue
            
            for wzorzec_gotowosci in WZORCE_GOTOWOSCI:
                if re.search(wzorzec_gotowosci + r'\s*$', output):
                    time.sleep(dodatkowe_oczekiwanie)
                    while shell.recv_ready():
                        output += shell.recv(4096).decode('utf-8', errors='ignore')
                    return output
        else:
            time.sleep(0.1)
    
    return output


def wyslij_komende(shell, komenda, timeout=10, dodatkowe_oczekiwanie=0.5):
    while shell.recv_ready():
        shell.recv(4096)
    
    shell.send(f"{komenda}\n")
    return czytaj_do_promptu(shell, timeout=timeout, dodatkowe_oczekiwanie=dodatkowe_oczekiwanie)


def pobierz_aktualny_hostname(shell):
    output = wyslij_komende(shell, "", timeout=5)
    return wyciagnij_hostname_z_promptu(output)


def wejdz_do_system_view(shell, max_prob=3):
    """
    Upewnia sie ze jestesmy w trybie system-view [hostname].
    Jesli jestesmy w <hostname>, wysyla 'system-view'.
    """
    for i in range(max_prob):
        output = wyslij_komende(shell, "", timeout=5)
        debug_print(f"Sprawdzam tryb, output: {repr(output[-50:])}")
        
        if czy_tryb_system_view(output):
            debug_print("Jestesmy w trybie system-view [hostname]")
            return True
        
        if czy_tryb_uzytkownika(output):
            debug_print(f"W trybie uzytkownika, wysylam system-view (proba {i+1})")
            output = wyslij_komende(shell, "system-view", timeout=5)
            
            if czy_tryb_system_view(output):
                debug_print("Po system-view jestesmy w trybie uprzywilejowanym")
                return True
    
    wyswietl_status(f"Nie udalo sie wejsc do trybu system-view po {max_prob} probach", "blad")
    return False


def wyjdz_do_trybu_uzytkownika(shell, max_prob=5):
    """
    Upewnia sie ze jestesmy w trybie uzytkownika <hostname>.
    Wysyla 'quit' az do osiagniecia trybu uzytkownika.
    """
    for i in range(max_prob):
        output = wyslij_komende(shell, "", timeout=5)
        
        if czy_tryb_uzytkownika(output):
            return True
        
        output = wyslij_komende(shell, "quit", timeout=5)
        
        if czy_tryb_uzytkownika(output):
            return True
    
    return False


def czekaj_na_prompt_po_logowaniu(shell, timeout=20):
    output = ""
    czas_startu = time.time()
    
    while True:
        if time.time() - czas_startu > timeout:
            break
        
        if shell.recv_ready():
            fragment = shell.recv(4096).decode('utf-8', errors='ignore')
            output += fragment
            debug_print(f"Login output: {repr(fragment)}")
            
            for wzorzec, odpowiedz in OBSLUGA_PROMPTOW.items():
                if re.search(wzorzec, output, re.IGNORECASE | re.DOTALL):
                    shell.send(f"{odpowiedz}\n")
                    time.sleep(0.5)
                    output = ""
                    break
            
            for wzorzec_gotowosci in WZORCE_GOTOWOSCI:
                if re.search(wzorzec_gotowosci + r'\s*$', output):
                    return output
        else:
            time.sleep(0.1)
    
    return output


def polacz_stelnet_ze_switchem(shell, ip, uzytkownik, haslo, hostname_cpe, timeout=30):
    """
    Wykonuje polaczenie stelnet do switcha.
    WAZNE: Musi byc wykonane z trybu system-view [hostname]!
    
    Zwraca tuple (sukces: bool, hostname_switch: str lub None, komunikat_bledu: str)
    """
    debug_print(f"Rozpoczynam stelnet do {ip}")
    
    while shell.recv_ready():
        shell.recv(4096)
    
    shell.send(f"stelnet {ip}\n")
    
    output = ""
    czas_startu = time.time()
    
    username_sent = False
    password_sent = False
    
    while True:
        if time.time() - czas_startu > timeout:
            debug_print("Timeout!")
            return False, None, "Timeout podczas laczenia ze switchem"
        
        if shell.recv_ready():
            fragment = shell.recv(4096).decode('utf-8', errors='ignore')
            output += fragment
            debug_print(f"Otrzymano: {repr(fragment)}")
            
            # Blad - komenda nierozpoznana
            if re.search(r'Error:.*Unrecognized command', output, re.IGNORECASE):
                return False, None, "Komenda stelnet nierozpoznana - upewnij sie ze jestes w trybie system-view"
            
            # Blad polaczenia
            if re.search(r'(Connection refused|Connection timed out|Unable to connect)', output, re.IGNORECASE):
                return False, None, "Blad polaczenia - host nieosiagalny"
            
            # Prompt username
            if re.search(r'(Username:|Please input the username:)\s*$', output, re.IGNORECASE):
                if not username_sent:
                    debug_print(f"Wykryto prompt username, wysylam: {uzytkownik}")
                    time.sleep(0.3)
                    shell.send(f"{uzytkownik}\n")
                    username_sent = True
                    output = ""
                continue
            
            # Prompt password
            if re.search(r'(Enter password:|Password:)\s*$', output, re.IGNORECASE):
                if not password_sent:
                    debug_print("Wykryto prompt password, wysylam haslo")
                    time.sleep(0.3)
                    shell.send(f"{haslo}\n")
                    password_sent = True
                    output = ""
                continue
            
            # Prompt zmiany hasla
            if re.search(r'Change now\?\s*\[Y/N\]:?', output, re.IGNORECASE):
                debug_print("Wykryto prompt zmiany hasla, wysylam: N")
                time.sleep(0.3)
                shell.send("N\n")
                output = ""
                continue
            
            # Prompty SSH Y/N
            if re.search(r'Continue to access it\?\s*\[Y/N\]:?', output, re.IGNORECASE):
                debug_print("Wykryto prompt SSH auth, wysylam: Y")
                time.sleep(0.3)
                shell.send("Y\n")
                output = ""
                continue
            
            if re.search(r"Save the server's public key\?\s*\[Y/N\]:?", output, re.IGNORECASE):
                debug_print("Wykryto prompt save key, wysylam: Y")
                time.sleep(0.3)
                shell.send("Y\n")
                output = ""
                continue
            
            # Blad autentykacji
            if re.search(r'(Authentication failed|Login failed|Access denied|Wrong password)', output, re.IGNORECASE):
                return False, None, "Blad autentykacji - sprawdz haslo switcha"
            
            # Sprawdz hostname
            hostname_match = re.search(r'[<\[]~?([\w\-]+)[>\]]\s*$', output)
            if hostname_match and password_sent:
                nowy_hostname = hostname_match.group(1)
                debug_print(f"Wykryto hostname: {nowy_hostname}")
                
                if nowy_hostname.lower() == hostname_cpe.lower():
                    debug_print(f"Hostname wciaz {nowy_hostname}, czekam...")
                    if password_sent and (time.time() - czas_startu > 15):
                        return False, None, f"Polaczenie nieudane - wciaz na {nowy_hostname}"
                else:
                    debug_print(f"Hostname zmienil sie na: {nowy_hostname}")
                    return True, nowy_hostname, None
        else:
            time.sleep(0.1)
    
    return False, None, "Nieoczekiwany blad"


def polacz_ssh_ze_switchem_z_cisco(shell, ip, uzytkownik, haslo, hostname_cpe, timeout=30):
    """
    SSH z routera Cisco do switcha Huawei.
    Zwraca tuple (sukces: bool, hostname_switch: str lub None, komunikat_bledu: str)
    """
    debug_print(f"Rozpoczynam SSH do {ip}")
    
    while shell.recv_ready():
        shell.recv(4096)
    
    shell.send(f"ssh -l {uzytkownik} {ip}\n")
    
    output = ""
    czas_startu = time.time()
    password_sent = False
    
    while True:
        if time.time() - czas_startu > timeout:
            return False, None, "Timeout podczas laczenia ze switchem"
        
        if shell.recv_ready():
            fragment = shell.recv(4096).decode('utf-8', errors='ignore')
            output += fragment
            debug_print(f"Otrzymano: {repr(fragment)}")
            
            if re.search(r'(Connection refused|Connection timed out|Unable to connect)', output, re.IGNORECASE):
                return False, None, f"Blad polaczenia"
            
            if re.search(r'Are you sure you want to continue connecting.*\?', output, re.IGNORECASE):
                debug_print("Wykryto prompt SSH key, wysylam: yes")
                shell.send("yes\n")
                time.sleep(0.3)
                output = ""
                continue
            
            if re.search(r'Password:\s*$', output, re.IGNORECASE) and not password_sent:
                debug_print("Wykryto prompt password, wysylam haslo")
                shell.send(f"{haslo}\n")
                password_sent = True
                time.sleep(0.3)
                output = ""
                continue
            
            if re.search(r'Change now\?\s*\[Y/N\]:?', output, re.IGNORECASE):
                debug_print("Wykryto prompt zmiany hasla, wysylam: N")
                shell.send("N\n")
                time.sleep(0.3)
                output = ""
                continue
            
            if re.search(r'(Authentication failed|Login failed|Access denied)', output, re.IGNORECASE):
                return False, None, "Blad autentykacji"
            
            hostname_match = re.search(r'[<\[]~?([\w\-]+)[>\]]\s*$', output)
            if hostname_match and password_sent:
                nowy_hostname = hostname_match.group(1)
                
                if nowy_hostname.lower() != hostname_cpe.lower():
                    return True, nowy_hostname, None
                elif (time.time() - czas_startu > 15):
                    return False, None, f"Polaczenie nieudane - wciaz na {nowy_hostname}"
        else:
            time.sleep(0.1)
    
    return False, None, "Nieoczekiwany blad"


# GLOWNE PROCESY

def uruchom_proces_huawei():
    print("\n" + "="*60)
    print("  Program do symulacji ruchu na SW (Huawei CPE)")
    print("="*60)

    adres_ip = input("\n\tWpisz IP CPE: ")
    uzytkownik = input("\tWpisz swoj user radius: ")
    haslo = getpass.getpass("\tWpisz haslo radius: ")
    ostatni_oktet = input("\tWpisz ostatni oktet do IP SW (np. 21): ")
    
    numer_vlan = input("\tWpisz numer VLAN do testu (np. 500, 510, 550): ").strip()
    if not numer_vlan.isdigit():
        wyswietl_status("Nieprawidlowy numer VLAN", "blad")
        return
    
    klient = paramiko.SSHClient()
    klient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        wyswietl_status(f"Laczenie z CPE ({adres_ip})...", "info")
        klient.connect(hostname=adres_ip, username=uzytkownik, password=haslo, timeout=TIMEOUT_POLACZENIA)
    except Exception as e:
        wyswietl_status(f"Blad polaczenia: {e}", "blad")
        return
    
    shell = klient.invoke_shell()
    time.sleep(2)
    
    czekaj_na_prompt_po_logowaniu(shell, timeout=TIMEOUT_POLACZENIA)
    
    hostname_cpe = pobierz_aktualny_hostname(shell)
    if not hostname_cpe:
        wyswietl_status("Nie udalo sie pobrac hostname CPE", "blad")
        klient.close()
        return
    
    wyswietl_status(f"Polaczono z CPE: {hostname_cpe}", "ok")
    
    # Wejdz do system-view
    wyslij_komende(shell, "system-view", timeout=TIMEOUT_KOMENDY)
    
    # Wydobycie trzeciego oktetu dla wybranego VLAN
    output = wyslij_komende(shell, "display ip interface brief", timeout=TIMEOUT_KOMENDY)
    
    wzorzec_vlan = rf'Vlanif{numer_vlan}\s+\d+\.(\d+)\.(\d+)\.\d+'
    dopasowanie = re.search(wzorzec_vlan, output)
    if dopasowanie:
        trzeci_oktet = dopasowanie.group(2)
        wyswietl_status(f"Znaleziono Vlanif{numer_vlan}, trzeci oktet: {trzeci_oktet}", "ok")
    else:
        wyswietl_status(f"Nie znaleziono adresu IP dla Vlanif{numer_vlan}", "blad")
        klient.close()
        return
    
    # === WAZNE: Upewnij sie ze jestesmy w system-view przed stelnet ===
    wyswietl_status("Sprawdzanie trybu system-view...", "info")
    if not wejdz_do_system_view(shell):
        wyswietl_status("Nie udalo sie wejsc do trybu system-view [hostname]", "blad")
        klient.close()
        return
    wyswietl_status("Tryb system-view aktywny - mozna wykonac stelnet", "ok")
    
    # Polaczenie ze switchem
    ip_switcha = f"195.166.10.{ostatni_oktet}"
    wyswietl_status(f"Laczenie ze switchem ({ip_switcha})...", "info")
    
    sukces, hostname_switch, blad = polacz_stelnet_ze_switchem(
        shell, ip_switcha, "user", "haslo", hostname_cpe, timeout=TIMEOUT_POLACZENIA
    )
    
    if not sukces:
        wyswietl_status(f"Nie udalo sie polaczyc ze switchem: {blad}", "blad")
        klient.close()
        return
    
    wyswietl_status(f"Polaczono ze switchem: {hostname_switch}", "ok")
    
    if hostname_switch.lower() == hostname_cpe.lower():
        wyswietl_status(f"BLAD KRYTYCZNY: Hostname switcha ({hostname_switch}) jest taki sam jak CPE!", "blad")
        wyswietl_status("Polaczenie prawdopodobnie nie powiodlo sie.", "blad")
        klient.close()
        return
    
    # Potwierdzenie uzytkownika
    print(f"\n{'='*60}")
    print("PODSUMOWANIE PLANOWANYCH ZMIAN:")
    print(f"{'='*60}")
    print(f"  CPE: {hostname_cpe}")
    print(f"  Switch docelowy: {hostname_switch}")
    print(f"  IP switcha: {ip_switcha}")
    print(f"  VLAN: {numer_vlan}")
    print(f"  Nowy IP Vlanif{numer_vlan}: 195.166.{trzeci_oktet}.155/24")
    print(f"  Nowa trasa domyslna: 195.166.{trzeci_oktet}.1")
    print(f"{'='*60}")
    
    if not potwierdz_operacje("Czy na pewno chcesz wykonac zmiany na SWITCHU?"):
        wyswietl_status("Operacja anulowana przez uzytkownika.", "uwaga")
        klient.close()
        return
    
    # Konfiguracja
    wyswietl_status("Rozpoczynam konfiguracje switcha...", "info")
    
    # Weryfikacja przed zmianami
    aktualny_host = pobierz_aktualny_hostname(shell)
    if aktualny_host != hostname_switch:
        wyswietl_status(f"BLAD: Hostname sie zmienil! Oczekiwano '{hostname_switch}', jest '{aktualny_host}'", "blad")
        klient.close()
        return
    
    ip_vlan_switcha = f"195.166.{trzeci_oktet}.155"
    wyslij_komende(shell, "system-view", timeout=TIMEOUT_KOMENDY)
    wyslij_komende(shell, f"interface Vlanif {numer_vlan}", timeout=TIMEOUT_KOMENDY)
    wyslij_komende(shell, f"ip address {ip_vlan_switcha} 255.255.255.0", timeout=TIMEOUT_KOMENDY)
    wyslij_komende(shell, "quit", timeout=TIMEOUT_KOMENDY)
    
    wyslij_komende(shell, "undo ip route-static 0.0.0.0 0.0.0.0 195.166.10.1", timeout=TIMEOUT_KOMENDY)
    trasa_statyczna = f"195.166.{trzeci_oktet}.1"
    wyslij_komende(shell, f"ip route-static 0.0.0.0 0.0.0.0 {trasa_statyczna}", timeout=TIMEOUT_KOMENDY)
    
    wyswietl_status("Konfiguracja zastosowana. Uruchamiam test ping...", "ok")
    
    # Test ping
    print("\n--- WYNIK PING ---")
    output = wyslij_komende(shell, "ping 9.9.9.9", timeout=15)
    dopasowanie_ping = re.search(r'(PING.*?packet loss.*?$)', output, re.DOTALL | re.MULTILINE)
    if dopasowanie_ping:
        print(dopasowanie_ping.group(1))
    else:
        print(output)
    print("--- KONIEC PING ---\n")
    
    # Weryfikacja przed przywracaniem
    aktualny_host = pobierz_aktualny_hostname(shell)
    if aktualny_host != hostname_switch:
        wyswietl_status(f"BLAD KRYTYCZNY: Hostname sie zmienil przed przywracaniem!", "blad")
        wyswietl_status(f"Oczekiwano '{hostname_switch}', jest '{aktualny_host}'", "blad")
        wyswietl_status("NIE PRZYWRACAM KONFIGURACJI - sprawdz recznie!", "uwaga")
        klient.close()
        return
    
    wyswietl_status("Przywracam pierwotna konfiguracje switcha...", "info")
    
    wyslij_komende(shell, "ip route-static 0.0.0.0 0.0.0.0 195.166.10.1", timeout=TIMEOUT_KOMENDY)
    wyslij_komende(shell, f"undo ip route-static 0.0.0.0 0.0.0.0 {trasa_statyczna}", timeout=TIMEOUT_KOMENDY)
    wyslij_komende(shell, f"undo interface Vlanif {numer_vlan}", timeout=TIMEOUT_KOMENDY)
    
    # Wyjdz z system-view przed save
    wyjdz_do_trybu_uzytkownika(shell)
    wyslij_komende(shell, "save", timeout=10)
    
    wyswietl_status(f"Konfiguracja switcha '{hostname_switch}' przywrocona i zapisana.", "ok")
    klient.close()


def uruchom_proces_cisco():
    print("\n" + "="*60)
    print("  Program do symulacji ruchu VLAN na SW (Cisco CPE)")
    print("="*60)

    adres_ip = input("\n\tWpisz IP CPE: ")
    uzytkownik = input("\tWpisz swoj user radius: ")
    haslo = getpass.getpass("\tWpisz haslo radius: ")
    ostatni_oktet = input("\tWpisz ostatni oktet do IP SW: ")
    
    numer_vlan = input("\tWpisz numer VLAN do testu (np. 100, 110, 150): ").strip()
    if not numer_vlan.isdigit():
        wyswietl_status("Nieprawidlowy numer VLAN", "blad")
        return
    
    klient = paramiko.SSHClient()
    klient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        wyswietl_status(f"Laczenie z CPE ({adres_ip})...", "info")
        klient.connect(hostname=adres_ip, username=uzytkownik, password=haslo, timeout=TIMEOUT_POLACZENIA)
    except Exception as e:
        wyswietl_status(f"Blad polaczenia: {e}", "blad")
        return
    
    shell = klient.invoke_shell()
    time.sleep(2)
    
    czekaj_na_prompt_po_logowaniu(shell, timeout=TIMEOUT_POLACZENIA)
    
    hostname_cpe = pobierz_aktualny_hostname(shell)
    if not hostname_cpe:
        wyswietl_status("Nie udalo sie pobrac hostname CPE", "blad")
        klient.close()
        return
    
    wyswietl_status(f"Polaczono z CPE: {hostname_cpe}", "ok")

    output = wyslij_komende(shell, f"show ip interface brief | include Vlan{numer_vlan}", timeout=TIMEOUT_KOMENDY)

    wzorzec_vlan = rf'Vlan{numer_vlan}\s+(\d+\.\d+)\.(\d+)\.\d+'
    dopasowanie = re.search(wzorzec_vlan, output)
    if dopasowanie:
        trzeci_oktet = dopasowanie.group(2)
        wyswietl_status(f"Znaleziono Vlan{numer_vlan}, trzeci oktet: {trzeci_oktet}", "ok")
    else:
        wyswietl_status(f"Nie udalo sie znalezc adresu IP dla Vlan{numer_vlan}.", "blad")
        klient.close()
        return

    ip_switcha = f"195.166.10.{ostatni_oktet}"
    wyswietl_status(f"Laczenie ze switchem ({ip_switcha})...", "info")
    
    sukces, hostname_switch, blad = polacz_ssh_ze_switchem_z_cisco(
        shell, ip_switcha, "user", "haslo", hostname_cpe, timeout=TIMEOUT_POLACZENIA
    )
    
    if not sukces:
        wyswietl_status(f"Nie udalo sie polaczyc ze switchem: {blad}", "blad")
        klient.close()
        return
    
    wyswietl_status(f"Polaczono ze switchem: {hostname_switch}", "ok")
    
    if hostname_switch.lower() == hostname_cpe.lower():
        wyswietl_status(f"BLAD KRYTYCZNY: Hostname switcha jest taki sam jak CPE!", "blad")
        klient.close()
        return
    
    print(f"\n{'='*60}")
    print("PODSUMOWANIE PLANOWANYCH ZMIAN:")
    print(f"{'='*60}")
    print(f"  CPE: {hostname_cpe}")
    print(f"  Switch docelowy: {hostname_switch}")
    print(f"  IP switcha: {ip_switcha}")
    print(f"  VLAN: {numer_vlan}")
    print(f"  Nowy IP Vlanif{numer_vlan}: 195.166.{trzeci_oktet}.155/24")
    print(f"  Nowa trasa domyslna: 195.166.{trzeci_oktet}.1")
    print(f"{'='*60}")
    
    if not potwierdz_operacje("Czy na pewno chcesz wykonac zmiany na SWITCHU?"):
        wyswietl_status("Operacja anulowana przez uzytkownika.", "uwaga")
        klient.close()
        return
    
    wyswietl_status("Rozpoczynam konfiguracje switcha...", "info")
    
    aktualny_host = pobierz_aktualny_hostname(shell)
    if aktualny_host != hostname_switch:
        wyswietl_status(f"BLAD: Hostname sie zmienil!", "blad")
        klient.close()
        return
    
    ip_vlan_switcha = f"195.166.{trzeci_oktet}.155"
    wyslij_komende(shell, "system-view", timeout=TIMEOUT_KOMENDY)
    wyslij_komende(shell, f"interface Vlanif {numer_vlan}", timeout=TIMEOUT_KOMENDY)
    wyslij_komende(shell, f"ip address {ip_vlan_switcha} 255.255.255.0", timeout=TIMEOUT_KOMENDY)
    wyslij_komende(shell, "quit", timeout=TIMEOUT_KOMENDY)
    
    wyslij_komende(shell, "undo ip route-static 0.0.0.0 0.0.0.0 195.166.10.1", timeout=TIMEOUT_KOMENDY)
    trasa_statyczna = f"195.166.{trzeci_oktet}.1"
    wyslij_komende(shell, f"ip route-static 0.0.0.0 0.0.0.0 {trasa_statyczna}", timeout=TIMEOUT_KOMENDY)
    
    wyswietl_status("Konfiguracja zastosowana. Uruchamiam test ping...", "ok")
    
    print("\n--- WYNIK PING ---")
    output = wyslij_komende(shell, "ping 9.9.9.9", timeout=15)
    dopasowanie_ping = re.search(r'(PING.*?packet loss.*?$)', output, re.DOTALL | re.MULTILINE)
    if dopasowanie_ping:
        print(dopasowanie_ping.group(1))
    else:
        print(output)
    print("--- KONIEC PING ---\n")
    
    aktualny_host = pobierz_aktualny_hostname(shell)
    if aktualny_host != hostname_switch:
        wyswietl_status(f"BLAD KRYTYCZNY: Hostname sie zmienil przed przywracaniem!", "blad")
        wyswietl_status("NIE PRZYWRACAM KONFIGURACJI - sprawdz recznie!", "uwaga")
        klient.close()
        return
    
    wyswietl_status("Przywracam pierwotna konfiguracje switcha...", "info")
    
    wyslij_komende(shell, "ip route-static 0.0.0.0 0.0.0.0 195.166.10.1", timeout=TIMEOUT_KOMENDY)
    wyslij_komende(shell, f"undo ip route-static 0.0.0.0 0.0.0.0 {trasa_statyczna}", timeout=TIMEOUT_KOMENDY)
    wyslij_komende(shell, f"undo interface Vlanif {numer_vlan}", timeout=TIMEOUT_KOMENDY)
    
    wyjdz_do_trybu_uzytkownika(shell)
    wyslij_komende(shell, "save", timeout=10)
    
    wyswietl_status(f"Konfiguracja switcha '{hostname_switch}' przywrocona i zapisana.", "ok")
    klient.close()


# PUNKT WEJSCIA

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  SYMULACJA RUCHU VLAN")
    print("="*60)
    print("\nZabezpieczenia:")
    print("  - Porownanie hostname CPE vs Switch")
    print("  - Weryfikacja ze hostname sie zmienil po stelnet")
    print("  - Potwierdzenie uzytkownika przed zmianami")
    print("  - Sprawdzanie hostname przed kazda krytyczna operacja")
    print("  - Wybor numeru VLAN")
    print("  - Weryfikacja trybu system-view przed stelnet")
    
    debug_input = input("\nWlaczyc tryb debug? (t/n): ").strip().lower()
    if debug_input in ['t', 'tak', 'y', 'yes']:
        TRYB_DEBUG = True
        print("Tryb debug WLACZONY - zobaczysz surowy output\n")
    
    while True:
        typ_urzadzenia = input("\n\tWybierz urzadzenie CPE (hua/cisco): ").strip().lower()
        if typ_urzadzenia == "hua":
            uruchom_proces_huawei()
        elif typ_urzadzenia == "cisco":
            uruchom_proces_cisco()
        else:
            print("Nieprawidlowy wybor. Wpisz 'hua' lub 'cisco'.")
            continue
        
        restart = input("\nProces zakonczony. Nacisnij 'r' i enter zeby uruchomic ponownie lub tylko enter zeby wyjsc: ")
        if restart.lower() != 'r':
            break
