"""
Nyx Light — Prošireni kontni plan za RH (RRiF standard)

Minimalno 100 najčešćih konta za računovodstveni ured.
Koristi se za:
- Prijedlog kontiranja (Modul A3)
- Validaciju knjiženja
- Izvještavanje

Referenca: RRiF kontni plan za poduzetnike
"""

# Razred 0: Dugotrajna imovina
RAZRED_0 = {
    "0100": "Koncesije, patenti, licencije",
    "0110": "Goodwill",
    "0120": "Software i razvoj",
    "0190": "Ispravak vrijednosti nematerijalne imovine",
    "0200": "Zemljišta",
    "0210": "Građevinski objekti",
    "0220": "Postrojenja i oprema",
    "0230": "Alati, pogonski i uredski inventar",
    "0240": "Transportna sredstva",
    "0250": "Biološka imovina",
    "0260": "Ulaganja u nekretnine",
    "0290": "Ispravak vrijednosti materijalne imovine",
    "0300": "Dugoročna financijska imovina — udjeli",
    "0310": "Dugoročni krediti dani",
    "0320": "Dugoročna potraživanja",
    "0330": "Dugoročna ulaganja u vrijednosne papire",
    "0400": "Dani depoziti i kaucije",
}

# Razred 1: Kratkotrajna imovina
RAZRED_1 = {
    "1000": "Sirovine i materijal na skladištu",
    "1010": "Rezervni dijelovi",
    "1020": "Sitan inventar na skladištu",
    "1030": "Ambalaža",
    "1100": "Nedovršena proizvodnja",
    "1200": "Potraživanja od kupaca u zemlji",
    "1201": "Potraživanja od kupaca u EU",
    "1202": "Potraživanja od kupaca izvan EU",
    "1209": "Ispravak vrijednosti potraživanja od kupaca",
    "1210": "Potraživanja za dane zajmove",
    "1220": "Potraživanja od zaposlenika",
    "1230": "Potraživanja od države — pretporez",
    "1231": "Potraživanja za povrat PDV-a",
    "1240": "Potraživanja od države — porez na dobit (pretplata)",
    "1250": "Ostala potraživanja",
    "1300": "Kratkoročna financijska imovina",
    "1310": "Dani kratkoročni krediti",
    "1400": "Gotovina u blagajni — kunska (EUR)",
    "1410": "Gotovina u blagajni — devizna",
    "1500": "Žiro račun — poslovna banka",
    "1510": "Devizni račun",
    "1520": "Izdvojeni depoziti",
    "1600": "Aktivna vremenska razgraničenja",
    "1610": "Unaprijed plaćeni troškovi",
    "1620": "Nedospjeli prihodi",
    "1900": "Unaprijed plaćeni troškovi — razgraničenja",
}

# Razred 2: Kapital i rezerve
RAZRED_2 = {
    "2000": "Temeljni kapital — upisani",
    "2010": "Temeljni kapital — uplaćeni",
    "2100": "Kapitalne rezerve — premija na dionice",
    "2200": "Rezerve iz dobiti — zakonske rezerve",
    "2210": "Rezerve za vlastite dionice / udjele",
    "2220": "Statutarne rezerve",
    "2300": "Revalorizacijske rezerve",
    "2400": "Zadržana dobit",
    "2410": "Preneseni gubitak",
    "2500": "Dobit tekuće godine",
    "2510": "Gubitak tekuće godine",
}

# Razred 3: Dugoročne obveze
RAZRED_3 = {
    "3000": "Obveze za primljene dugoročne kredite od banaka",
    "3010": "Obveze za primljene dugoročne kredite od poduzetnika",
    "3020": "Obveze po izdanim obveznicama",
    "3100": "Obveze prema povezanim osobama — dugoročne",
    "3200": "Dugoročna rezerviranja za rizike i troškove",
    "3210": "Rezerviranja za sudske sporove",
    "3220": "Rezerviranja za otpremnine",
    "3230": "Rezerviranja za jamstva",
    "3300": "Odgođene porezne obveze",
    "3400": "Ostale dugoročne obveze",
}

# Razred 4: Kratkoročne obveze
RAZRED_4 = {
    "4000": "Obveze prema dobavljačima u zemlji",
    "4010": "Obveze prema dobavljačima u EU",
    "4020": "Obveze prema dobavljačima izvan EU",
    "4100": "Obveze za kratkoročne kredite od banaka",
    "4110": "Obveze po kreditnim karticama",
    "4120": "Obveze za električna energija (HEP)",
    "4130": "Obveze za telekomunikacije (HT, A1...)",
    "4140": "Obveze za najamnine",
    "4200": "Obveze za plaće — neto",
    "4210": "Obveze za doprinose iz plaće (MIO I)",
    "4211": "Obveze za doprinose iz plaće (MIO II)",
    "4220": "Obveze za porez na dohodak iz plaće",
    "4221": "Obveze za prirez iz plaće",
    "4230": "Obveze za doprinos za zdravstveno (na plaću)",
    "4240": "Obveze za isplatu autorskih honorara",
    "4250": "Obveze za isplatu ugovora o djelu",
    "4300": "Obveze za porez na dodanu vrijednost — PDV",
    "4310": "Obveze za porez na dobit",
    "4320": "Obveze za porez po odbitku",
    "4330": "Obveze za lokalne poreze",
    "4400": "Obveze za obračunatu amortizaciju",
    "4420": "Troškovi vrijednosnih usklađenja potraživanja",
    "4500": "Pasivna vremenska razgraničenja",
    "4510": "Unaprijed naplaćeni prihodi",
    "4520": "Odgođeno plaćanje troškova",
}

# Razred 5: Troškovi (po vrsti)
RAZRED_5 = {
    "5000": "Troškovi sirovina i materijala",
    "5010": "Troškovi sitnog inventara",
    "5020": "Troškovi energije (struja, plin, gorivo)",
    "5030": "Troškovi rezervnih dijelova",
    "5100": "Troškovi usluga — izrada",
    "5110": "Troškovi prijevoza i dostave",
    "5120": "Troškovi održavanja i popravaka",
    "5130": "Troškovi zakupa i najma",
    "5140": "Troškovi telefona i interneta",
    "5150": "Troškovi komunalnih usluga",
    "5160": "Troškovi intelektualnih usluga (računovodstvo, savjetovanje, revizija)",
    "5170": "Troškovi promidžbe i reklame",
    "5180": "Troškovi bankovnih usluga i platnog prometa",
    "5190": "Troškovi osiguranja",
    "5200": "Troškovi bruto plaća",
    "5210": "Troškovi doprinosa na plaće",
    "5220": "Troškovi naknada (topli obrok, prijevoz)",
    "5230": "Troškovi otpremnina",
    "5240": "Troškovi regresa",
    "5250": "Troškovi darova zaposlenicima",
    "5300": "Amortizacija materijalne imovine",
    "5310": "Amortizacija nematerijalne imovine",
    "5400": "Troškovi reprezentacije (100% — 50% porezno nepriznato)",
    "5410": "Troškovi službenih putovanja — dnevnice",
    "5420": "Troškovi službenih putovanja — km naknada",
    "5430": "Troškovi službenih putovanja — smještaj",
    "5440": "Troškovi službenih putovanja — ostalo",
    "5500": "Vrijednosno usklađenje kratkotrajne imovine",
    "5600": "Rezerviranja za troškove i rizike",
    "5900": "Ostali troškovi poslovanja",
}

# Razred 6: Prihodi
RAZRED_6 = {
    "6000": "Prihodi od prodaje proizvoda",
    "6010": "Prihodi od prodaje robe",
    "6020": "Prihodi od pružanja usluga u zemlji",
    "6021": "Prihodi od pružanja usluga u EU",
    "6022": "Prihodi od pružanja usluga izvan EU",
    "6100": "Prihodi od najma i zakupa",
    "6200": "Prihodi od kamata",
    "6210": "Prihodi od tečajnih razlika",
    "6300": "Prihodi od naplate otpisanih potraživanja",
    "6400": "Ostali poslovni prihodi",
    "6500": "Prihodi od ukidanja rezerviranja",
    "6600": "Izvanredni prihodi",
    "6700": "Prihodi od potpore i subvencija",
}

# Razred 7: Rashodi (rezultatski — koristi se u nekim kontnim planovima)
RAZRED_7 = {
    "7000": "Materijalni troškovi",
    "7100": "Troškovi prodane robe — nabavna vrijednost",
    "7200": "Troškovi usluga",
    "7300": "Amortizacija",
    "7400": "Ostali troškovi poslovanja",
    "7500": "Troškovi osoblja",
    "7600": "Financijski rashodi",
    "7610": "Rashodi od kamata",
    "7620": "Rashodi od tečajnih razlika",
    "7700": "Rashodi od vrijednosnog usklađenja",
    "7800": "Ostali rashodi",
    "7900": "Izvanredni rashodi",
}

# Razred 8: Rezultat
RAZRED_8 = {
    "8000": "Ukupni prihodi",
    "8100": "Ukupni rashodi",
    "8200": "Dobit prije oporezivanja",
    "8300": "Porez na dobit",
    "8400": "Dobit razdoblja",
    "8500": "Gubitak razdoblja",
}

# Razred 9: Izvanbilančna evidencija
RAZRED_9 = {
    "9000": "Tuđa imovina (primljena u komisiju, konsignaciju)",
    "9100": "Dana jamstva i garancije",
    "9200": "Primljeni instrumenti osiguranja",
}


def get_full_kontni_plan() -> dict:
    """Vrati kompletni kontni plan."""
    plan = {}
    for razred in [RAZRED_0, RAZRED_1, RAZRED_2, RAZRED_3, RAZRED_4,
                   RAZRED_5, RAZRED_6, RAZRED_7, RAZRED_8, RAZRED_9]:
        plan.update(razred)
    return plan


def get_konto_name(konto: str) -> str:
    """Dohvati naziv konta."""
    plan = get_full_kontni_plan()
    return plan.get(konto, "Nepoznat konto")


def suggest_konto_by_keyword(keyword: str) -> list:
    """Pretraži kontni plan po ključnoj riječi."""
    plan = get_full_kontni_plan()
    keyword_lower = keyword.lower()
    results = []
    for konto, name in plan.items():
        if keyword_lower in name.lower():
            results.append({"konto": konto, "name": name})
    return results


# Statistika
TOTAL_KONTA = len(get_full_kontni_plan())
