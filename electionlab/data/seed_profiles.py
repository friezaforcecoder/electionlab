"""Built-in offline starter profiles for ElectionLab.

0.10 upgrades the starter pack from mostly-neutral placeholders to a more useful
*starter-enriched* simulation pack. Numerical traits are explicitly game-model
heuristics, not objective ratings. Historical/current political positions are
still not silently invented: unknown issue positions remain unknown until the
profile is researched or the user edits it.
"""

from __future__ import annotations

from datetime import date


PRESIDENTS = [
("George Washington",1732,"Independent","VA","1789–1797"),("John Adams",1735,"Federalist","MA","1797–1801"),
("Thomas Jefferson",1743,"Democratic-Republican","VA","1801–1809"),("James Madison",1751,"Democratic-Republican","VA","1809–1817"),
("James Monroe",1758,"Democratic-Republican","VA","1817–1825"),("John Quincy Adams",1767,"Democratic-Republican / National Republican","MA","1825–1829"),
("Andrew Jackson",1767,"Democratic","TN","1829–1837"),("Martin Van Buren",1782,"Democratic","NY","1837–1841"),
("William Henry Harrison",1773,"Whig","OH","1841"),("John Tyler",1790,"Whig","VA","1841–1845"),
("James K. Polk",1795,"Democratic","TN","1845–1849"),("Zachary Taylor",1784,"Whig","LA","1849–1850"),
("Millard Fillmore",1800,"Whig","NY","1850–1853"),("Franklin Pierce",1804,"Democratic","NH","1853–1857"),
("James Buchanan",1791,"Democratic","PA","1857–1861"),("Abraham Lincoln",1809,"Republican","IL","1861–1865"),
("Andrew Johnson",1808,"Democratic / National Union","TN","1865–1869"),("Ulysses S. Grant",1822,"Republican","IL","1869–1877"),
("Rutherford B. Hayes",1822,"Republican","OH","1877–1881"),("James A. Garfield",1831,"Republican","OH","1881"),
("Chester A. Arthur",1829,"Republican","NY","1881–1885"),("Grover Cleveland",1837,"Democratic","NY","1885–1889; 1893–1897"),
("Benjamin Harrison",1833,"Republican","IN","1889–1893"),("William McKinley",1843,"Republican","OH","1897–1901"),
("Theodore Roosevelt",1858,"Republican","NY","1901–1909"),("William Howard Taft",1857,"Republican","OH","1909–1913"),
("Woodrow Wilson",1856,"Democratic","NJ","1913–1921"),("Warren G. Harding",1865,"Republican","OH","1921–1923"),
("Calvin Coolidge",1872,"Republican","MA","1923–1929"),("Herbert Hoover",1874,"Republican","CA","1929–1933"),
("Franklin D. Roosevelt",1882,"Democratic","NY","1933–1945"),("Harry S. Truman",1884,"Democratic","MO","1945–1953"),
("Dwight D. Eisenhower",1890,"Republican","KS","1953–1961"),("John F. Kennedy",1917,"Democratic","MA","1961–1963"),
("Lyndon B. Johnson",1908,"Democratic","TX","1963–1969"),("Richard Nixon",1913,"Republican","CA","1969–1974"),
("Gerald Ford",1913,"Republican","MI","1974–1977"),("Jimmy Carter",1924,"Democratic","GA","1977–1981"),
("Ronald Reagan",1911,"Republican","CA","1981–1989"),("George H. W. Bush",1924,"Republican","TX","1989–1993"),
("Bill Clinton",1946,"Democratic","AR","1993–2001"),("George W. Bush",1946,"Republican","TX","2001–2009"),
("Barack Obama",1961,"Democratic","IL","2009–2017"),("Donald Trump",1946,"Republican","FL","2017–2021; 2025–present"),
("Joe Biden",1942,"Democratic","DE","2021–2025")
]

PUBLIC_FIGURES = [
("Taylor Swift","Musician"),("Beyoncé","Musician"),("Dwayne Johnson","Actor / entertainer"),("Keanu Reeves","Actor"),
("Leonardo DiCaprio","Actor"),("Tom Cruise","Actor"),("Robert Downey Jr.","Actor"),("Chris Evans","Actor"),
("Scarlett Johansson","Actor"),("Zendaya","Actor / musician"),("Ryan Reynolds","Actor"),("Hugh Jackman","Actor"),
("Margot Robbie","Actor"),("Pedro Pascal","Actor"),("Jenna Ortega","Actor"),("Timothée Chalamet","Actor"),
("Selena Gomez","Musician / actor"),("Ariana Grande","Musician / actor"),("Billie Eilish","Musician"),("Lady Gaga","Musician / actor"),
("Drake","Musician"),("Kendrick Lamar","Musician"),("Eminem","Musician"),("Snoop Dogg","Musician / entertainer"),
("Post Malone","Musician"),("The Weeknd","Musician"),("LeBron James","Athlete"),("Stephen Curry","Athlete"),
("Tom Brady","Athlete"),("Patrick Mahomes","Athlete"),("Shaquille O'Neal","Athlete / entertainer"),("Michael Jordan","Athlete / business"),
("MrBeast","Online creator"),("Markiplier","Online creator"),("PewDiePie","Online creator"),("Kai Cenat","Online creator"),
("IShowSpeed","Online creator"),("Joe Rogan","Podcaster / entertainer"),("Oprah Winfrey","TV personality / business"),("Jon Stewart","Comedian / TV host"),
("Stephen Colbert","Comedian / TV host"),("Jimmy Fallon","Comedian / TV host"),("Gordon Ramsay","Chef / TV personality"),("Elon Musk","Business / technology"),
("Mark Cuban","Business / TV personality"),("Jeff Bezos","Business / technology"),("Bill Gates","Business / technology / philanthropy"),("Neil deGrasse Tyson","Science communicator"),
("Mark Hamill","Actor"),("Harrison Ford","Actor")
]

# These are deliberately broad ElectionLab game-input heuristics. They are not
# claims about moral worth, intelligence, political correctness, or electoral
# destiny. Values can be replaced by researched/custom profiles at any time.
_PRESIDENT_TRAIT_OVERRIDES = {
    "George Washington": (82, 72, 78, 100, 2.0),
    "Thomas Jefferson": (70, 66, 82, 97, 1.0),
    "Andrew Jackson": (78, 63, 82, 92, 0.5),
    "Abraham Lincoln": (86, 84, 90, 100, 2.5),
    "Ulysses S. Grant": (62, 52, 92, 90, 0.0),
    "Theodore Roosevelt": (91, 78, 91, 98, 2.5),
    "Woodrow Wilson": (68, 72, 90, 91, 0.0),
    "Franklin D. Roosevelt": (92, 84, 96, 100, 3.0),
    "Harry S. Truman": (66, 65, 91, 91, 0.0),
    "Dwight D. Eisenhower": (75, 63, 98, 98, 2.0),
    "John F. Kennedy": (91, 86, 85, 100, 3.0),
    "Lyndon B. Johnson": (77, 75, 97, 95, 0.5),
    "Richard Nixon": (66, 78, 96, 99, -0.5),
    "Jimmy Carter": (64, 62, 88, 93, 0.0),
    "Ronald Reagan": (93, 84, 91, 100, 3.0),
    "George H. W. Bush": (65, 67, 96, 96, 0.5),
    "Bill Clinton": (91, 86, 92, 100, 3.0),
    "George W. Bush": (78, 67, 88, 100, 1.0),
    "Barack Obama": (94, 89, 91, 100, 3.5),
    "Donald Trump": (93, 78, 88, 100, 1.0),
    "Joe Biden": (72, 78, 99, 100, 0.5),
}

_PRESIDENT_RECOGNITION_HIGH = {
    "John Adams","James Madison","James Monroe","James K. Polk","Grover Cleveland","William McKinley",
    "William Howard Taft","Calvin Coolidge","Herbert Hoover","Gerald Ford"
}

# Public-figure recognition/communication estimates are only used as starter
# game inputs. Political stance fields remain empty unless sourced later.
_PUBLIC_TRAITS = {
    "Taylor Swift": (86,58,48,99,2.0), "Beyoncé": (88,57,50,98,2.0), "Dwayne Johnson": (88,62,50,97,2.5),
    "Keanu Reeves": (76,54,45,94,1.5), "Leonardo DiCaprio": (73,58,52,94,1.0), "Tom Cruise": (79,58,55,97,1.0),
    "Robert Downey Jr.": (83,62,50,94,1.5), "Chris Evans": (76,60,48,90,1.0), "Scarlett Johansson": (75,58,50,91,1.0),
    "Zendaya": (82,57,45,94,2.0), "Ryan Reynolds": (87,64,48,94,2.0), "Hugh Jackman": (84,60,50,91,2.0),
    "Margot Robbie": (79,56,46,91,1.5), "Pedro Pascal": (80,57,45,90,1.5), "Jenna Ortega": (74,50,38,88,1.0),
    "Timothée Chalamet": (76,52,42,89,1.0), "Selena Gomez": (78,55,45,94,1.5), "Ariana Grande": (78,54,44,96,1.0),
    "Billie Eilish": (74,50,40,94,1.0), "Lady Gaga": (90,67,55,96,2.0), "Drake": (76,48,45,97,0.0),
    "Kendrick Lamar": (79,58,45,92,1.0), "Eminem": (81,54,48,96,0.5), "Snoop Dogg": (88,60,50,96,2.0),
    "Post Malone": (76,48,40,92,1.0), "The Weeknd": (70,45,40,93,0.5), "LeBron James": (80,59,76,99,1.5),
    "Stephen Curry": (80,56,73,95,2.0), "Tom Brady": (79,60,83,97,1.0), "Patrick Mahomes": (78,55,70,92,1.5),
    "Shaquille O'Neal": (91,66,72,96,2.5), "Michael Jordan": (73,52,91,100,0.5), "MrBeast": (82,50,62,92,1.5),
    "Markiplier": (79,53,48,84,1.5), "PewDiePie": (76,50,50,89,0.5), "Kai Cenat": (82,48,40,83,1.0),
    "IShowSpeed": (82,43,35,81,0.0), "Joe Rogan": (82,70,70,95,0.0), "Oprah Winfrey": (94,82,83,99,3.0),
    "Jon Stewart": (91,88,72,93,2.5), "Stephen Colbert": (88,84,68,91,2.0), "Jimmy Fallon": (83,62,58,91,1.5),
    "Gordon Ramsay": (90,63,71,93,1.5), "Elon Musk": (77,58,92,100,-1.0), "Mark Cuban": (84,76,88,90,1.0),
    "Jeff Bezos": (61,48,94,96,-0.5), "Bill Gates": (69,63,95,98,0.5), "Neil deGrasse Tyson": (83,75,68,87,1.5),
    "Mark Hamill": (77,61,60,89,1.0), "Harrison Ford": (72,52,68,96,0.5),
}


def _president_traits(name: str) -> tuple[int,int,int,int,float]:
    if name in _PRESIDENT_TRAIT_OVERRIDES:
        return _PRESIDENT_TRAIT_OVERRIDES[name]
    recognition = 88 if name in _PRESIDENT_RECOGNITION_HIGH else 76
    # Charisma, debate/communication, experience, recognition, national appeal.
    return (60, 58, 92, recognition, 0.0)


def built_in_profiles():
    snapshot = date.today().isoformat()
    out = []
    for name, birth, party, state, years in PRESIDENTS:
        charisma, debate, experience, recognition, appeal = _president_traits(name)
        out.append({
            "canonical_name": name,
            "profile_type": "historical_political",
            "source_type": "built_in",
            "party": party,
            "home_state": state,
            "birth_year": birth,
            "career": "President of the United States",
            "office_years": years,
            "ideology": 0,
            "experience": experience,
            "name_recognition": recognition,
            "charisma": charisma,
            "debate_skill": debate,
            "national_appeal": appeal,
            "known_positions": {},
            "inferred_positions": {},
            "sources": [],
            "confidence": 0.72,
            "profile_status": "starter_enriched",
            "snapshot_date": snapshot,
            "starter_pack": "EL Starter Enrichment v2",
            "starter_note": "Numerical campaign traits are ElectionLab heuristics; issue positions remain unknown until sourced.",
        })
    for name, career in PUBLIC_FIGURES:
        charisma, debate, experience, recognition, appeal = _PUBLIC_TRAITS.get(name, (65,50,45,80,0.0))
        out.append({
            "canonical_name": name,
            "profile_type": "public_figure",
            "source_type": "built_in",
            "career": career,
            "ideology": 0,
            "experience": experience,
            "name_recognition": recognition,
            "charisma": charisma,
            "debate_skill": debate,
            "national_appeal": appeal,
            "known_positions": {},
            "inferred_positions": {},
            "sources": [],
            "confidence": 0.42,
            "profile_status": "starter_enriched",
            "snapshot_date": snapshot,
            "starter_pack": "EL Starter Enrichment v2",
            "starter_note": "Numerical campaign traits are ElectionLab heuristics; political positions remain unknown unless sourced.",
        })
    return out
