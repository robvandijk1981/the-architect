# Workforce Specialist Agent — Training Data Blueprint

**Doel:** De ultieme trainingsset voor een AI workforce specialist die CHRO's, CFO's en COO's vertrouwen als bron van waarheid over de Nederlandse arbeidsmarkt en workforce strategie.
**Versie:** 1.0 | 16 maart 2026
**Auteur:** Rob van Dijk & Claude (ModellenWerk)

---

## Ontwerpprincipe

Een CHRO vertrouwt deze agent pas als die méér weet dan de CHRO zelf. Dat betekent niet alleen "data hebben" maar ook: weten wat die data betekent, hoe die zich verhoudt tot andere sectoren, welke interventies bewezen werken, en welke regelgeving van toepassing is. De trainingsset is daarom gestructureerd in 7 kennislagen — van harde data tot strategisch adviesvermogen.

---

## LAAG 1: Harde Arbeidsmarktdata (Nederland)

### 1.1 CBS StatLine — Officiële Statistieken
| Dataset | Tabel-ID | Inhoud | Update |
|---------|----------|--------|--------|
| Beroepsbevolking & werkloosheid | 80590NED | Maandelijks: werkgelegenheid, werkloosheid, leeftijd/geslacht | Maandelijks |
| CAO-lonen geïndexeerd | 85663NED | Loonontwikkeling per sector (2020=100) | Kwartaal |
| CAO-lonen historisch | 82838NED | Loonontwikkeling vanaf 1972 | Kwartaal |
| Vacatures per sector | Diverse | Vacaturegraad, openstaande vacatures | Kwartaal |
| Ziekteverzuim | Diverse | Verzuimpercentage per sector, bedrijfsgrootte | Kwartaal |
| Arbeidsongeschiktheid | Diverse | WIA/WAO instroom per sector | Jaarlijks |
| Bevolkingsprognose | Diverse | Leeftijdsopbouw, vergrijzing 2030-2050 | Jaarlijks |
| Loonstructuuronderzoek | Diverse | Loonverdeling per functie/sector/opleiding | 2-jaarlijks |
| Werkgelegenheid per sector | Diverse | FTE en banen per SBI-code | Kwartaal |

**API:** OData v4 — `https://opendata.cbs.nl/statline/api/v1/` — gratis, geen auth
**Tooling:** Python `cbsodata`, R `cbsodataR`
**Kwaliteit:** Goudstandaard. 1-3 maanden vertraging.

### 1.2 UWV — Arbeidsmarktspanning & Vacatures
| Bron | URL | Inhoud | Update |
|------|-----|--------|--------|
| Spanningsindicator | uwv.nl/arbeidsmarktinformatie/dashboards | Spanning per 93 beroepsgroepen × regio | Kwartaal |
| Open Match Data | data.overheid.nl/dataset/uwv-open-match-data | Vacatures + CV's per 4-cijferig postcode | Continu |
| Beroepenkaart Data | data.overheid.nl/dataset/uwv-beroepenkaart-data | Beroepsspecifieke vacature- en skillsdata | Kwartaal |
| Sectorinformatie | uwv.nl/arbeidsmarktinformatie/sector | Per sector: status, vacatures, trends | Kwartaal |

### 1.3 Demografische Data & Projecties
| Bron | Inhoud | Waarde voor agent |
|------|--------|-------------------|
| CBS Bevolkingsprognose | Leeftijdsopbouw NL 2025-2070 | Vergrijzingsrisico berekenen |
| CBS Regionale prognose | Bevolking per gemeente/regio | Regionale arbeidsaanbod projecties |
| CPB Economische verkenning | BBP, werkgelegenheid, lonen prognose | Macro-economische context |
| CPB Centraal Economisch Plan | Werkloosheidsprognose, loongroei | Economische scenario's |
| PBL Regionale prognoses | Ruimtelijke economie | Woon-werkpatronen |

### 1.4 Opleidingsdata & Instroom
| Bron | URL | Inhoud |
|------|-----|--------|
| DUO Open Data | duo.nl/open-onderwijsdata | Studenten, afgestudeerden per opleiding × jaar |
| ROA Arbeidsmarktprognoses | roastatistics.maastrichtuniversity.nl | Arbeidsmarkt per opleiding, 2030-2040 projecties |
| ROA Talentvraag 2040 | Via ROA publicaties | Langetermijn skillsvraag |
| Nuffic | nuffic.nl | Internationale studenten in NL, brain gain/drain |
| SBB | s-bb.nl | Mbo leerbedrijven en stages, praktijkleren |

### 1.5 Regionale Arbeidsmarktdata
| Bron | URL | Inhoud |
|------|-----|--------|
| ArbeidsmarktInZicht | arbeidsmarktinzicht.nl | Integreert CBS+UWV+DUO+ROA+LISA per regio |
| LISA Werkgelegenheidsregister | lisa.nl | Alle vestigingen met betaald werk per gemeente |
| Provinciale arbeidsmarktmonitors | Per provincie | Regionale verdieping, beleidsadvies |

---

## LAAG 2: Sectorspecifieke Kennis

### 2.1 Sectormonitoren
| Sector | Monitor | URL | Kern-metrics |
|--------|---------|-----|-------------|
| Zorg & Welzijn | AZW Info + Prognosemodel | azwinfo.nl / prognosemodelzw.nl | 1.5M werknemers, tekort 62K→232K (2033) |
| Techniek & ICT | Techniekpact Monitor | techniekpactmonitor.nl | 1.9M werknemers, alle regio's krap |
| Bouw | EIB Arbeidsmarktrapportage | eib.nl | 356K banen, 60K extra nodig 2024-2028 |
| Overheid | ABP + Min. BZK | caorijk.nl / abp.nl | 3M deelnemers ABP, vergrijzingsgolf |
| Onderwijs | OCW + DUO | duo.nl | Lerarentekort, STEM-gat |
| Financieel | NVB + CBS | nvb.nl | Digitale transformatie, headcount-reductie |
| Retail | CBS + ArbeidsmarktInZicht | cbs.nl | E-commerce disruptie, flexwerk |
| Agri & Food | LTO + CBS | lto.nl | Seizoensarbeid, internationale werknemers |
| Hospitality | KHN + UWV | uwv.nl/sector/horeca | Hoog verloop, looncompetitiviteit |
| Transport | CBS + UWV | uwv.nl/sector/transport | Chauffeurstekort, elektrificatie |
| Energie | Netbeheerders + CBS | Diverse | Energietransitie, snelle groei, skills gap |

### 2.2 Sectorale Financiële Data
| Bron | Inhoud | Waarde |
|------|--------|--------|
| Jaarverslagservice.nl | Gedeponeerde jaarverslagen | Omzet, resultaat, FTE per organisatie |
| KvK Handelsregister Open Data | 2.6M vestigingen, dagelijks bijgewerkt | Bedrijfsomvang, sector, regio |
| CBS Financiën bedrijven | Omzet, winst, investeringen per sector | Sectorale financiële benchmarks |
| Benchmark Ziekenhuizen | Via NVZ | Financiële prestaties ziekenhuizen |
| Transparantiebenchmark | rijksoverheid.nl | MVO/ESG scores grote bedrijven |

### 2.3 Brancheorganisaties & Kennisinstituten
| Organisatie | Focus | Publicaties |
|-------------|-------|-------------|
| AWVN | Werkgeversvereniging | CAO-trends, loonkostenstijging, HR-benchmarks |
| VNO-NCW / MKB-Nederland | Werkgevers | Bedrijfsleven trends, arbeidsmarktstandpunten |
| FNV / CNV | Vakbonden | Werknemersperspectief, CAO-eisen, werkdruk |
| TNO | Arbeid & Gezondheid | Werkdruk, verzuim, duurzame inzetbaarheid |
| SCP | Sociaal-cultureel | Levensloop, werkbeleving, sociale trends |
| RIVM | Volksgezondheid | Beroepsziekten, gezondheidsrisico's per sector |
| A+O fondsen | Per sector | Sectorale scholings- en arbeidsmarktfondsen |
| STOOF | Uitzendbranche | Flexmarkt data en trends |

---

## LAAG 3: Regelgeving & Institutioneel Kader

Dit is waar de meeste AI-tools falen. De agent MOET dit weten.

### 3.1 Arbeidsrecht & Ontslagregels
| Onderwerp | Bron | Kernkennis |
|-----------|------|------------|
| Ontslagrecht | BW Boek 7, Titel 10 | Opzegverboden, transitievergoeding (1/3 maandsalaris per dienstjaar), UWV-route vs. kantonrechter |
| Wet Arbeidsmarkt in Balans (WAB) | Staatsblad 2019/219 | Ketenregeling (3 contracten in 3 jaar), oproepcontracten, payroll |
| Wet Werk en Zekerheid (WWZ) | Staatsblad 2014/216 | Transitievergoeding, aanzegplicht, opzegprocedure |
| Wet Transparante Arbeidsvoorwaarden | 2022 | Informatieplicht werkgever, verbod nevenwerkbeding |
| Detacheringsrichtlijn | EU 2018/957 | Gelijke beloning bij grensoverschrijdende detachering |
| WAADI | Uitzendwetgeving | Inlenersbeloning, allocatiefunctie |
| ZZP-wetgeving | In ontwikkeling | Schijnzelfstandigheid, handhaving Belastingdienst |

### 3.2 Sociale Zekerheid & Verzuim
| Wet/Regeling | Kernkennis voor agent |
|-------------|----------------------|
| Wet Verbetering Poortwachter | 2 jaar loondoorbetaling, re-integratieverplichting, plan van aanpak |
| WIA (WGA + IVA) | Arbeidsongeschiktheid >2 jaar, instroompremie, sectorpremie |
| Ziektewet | Vangnet voor flexwerkers, no-risk polis |
| WW | Duur afhankelijk van arbeidsverleden, maximaal 24 maanden |
| Pensioenwet + Wet Toekomst Pensioenen | Overgang naar defined contribution, transitieplan verplicht |
| STAP-budget / SLIM-regeling | Scholingssubsidies (verandert regelmatig, altijd checken) |

### 3.3 CAO-landschap
| Categorie | Bron | Inhoud |
|-----------|------|--------|
| CAO-teksten | Loonwijzer.nl/caowijzer | 749 variabelen per CAO, 12 thema's |
| CAO-register | caoparagraaf.minszw.nl | Officieel ministerieel register |
| CAO-kijker | cao-kijker.awvn.nl | Recente ontwikkelingen, loonstijging tracking |
| Sector-CAO's | Per sector | Zorg (CAO VVT, CAO GGZ, CAO Ziekenhuizen), Overheid (CAO Rijk), Bouw (CAO Bouwnijverheid), etc. |

### 3.4 Governance & Toezicht
| Regelgeving | Relevantie |
|-------------|-----------|
| WOR (Wet op de Ondernemingsraden) | Adviesrecht OR bij reorganisatie, instemmingsrecht bij arbeidsvoorwaarden |
| Corporate Governance Code | Beloningsbeleid, diversiteit bestuur |
| Wet Bestuur en Toezicht Rechtspersonen | Governance stichtingen en verenigingen |
| AI Act (EU) | Impact op HR-technologie: high-risk classificatie voor recruitment-AI |
| AVG/GDPR | Verwerking werknemersgegevens, DPIA bij HR-analytics |

---

## LAAG 4: Interventie-effectiviteit & Best Practices

De agent moet niet alleen problemen benoemen maar ook weten wat WERKT.

### 4.1 Verloop & Retentie
| Kennisgebied | Bronnen | Kerndata |
|-------------|---------|----------|
| Vervangingskosten per vertrek | SHRM, Gallup, sectorstudies | 0.5-2× jaarsalaris afhankelijk van functieniveau |
| Bewezen retentie-interventies | Academic research + praktijkstudies | Onboarding (verlaagt verloop 25%), loopbaanpaden, flexibiliteit |
| Exit-interview patronen | HR-analytics literatuur | Top-redenen: management, groeimogelijkheden, werk-privé, beloning |
| Verloopbenchmarks per sector NL | CBS + sectormonitoren | Zorg: 12-18%, ICT: 15-22%, Overheid: 6-10%, Retail: 20-30% |

### 4.2 Verzuim & Vitaliteit
| Kennisgebied | Bronnen | Kerndata |
|-------------|---------|----------|
| Verzuimoorzaken | TNO NEA/WEA, ArboNed/HumanCapitalCare | Fysiek (30%), mentaal (35%), werkdruk (20%), organisatorisch (15%) |
| Effectieve verzuiminterventies | Cochrane reviews, TNO | Vroege interventie (-30%), leiderschapstraining (-15%), werkplekanalyse |
| Werkdruk & burn-out | TNO Werkstress rapport | 1.3M werknemers burn-outklachten, €2.8B kosten/jaar |
| Duurzame inzetbaarheid | SER-advies | Levensfasebewust HR, scholing, mobiliteit |
| Verzuimbenchmarks per sector | CBS + ArboNed | Zorg: 6.5-8%, Overheid: 5-6%, Industrie: 4-5%, ICT: 3-4% |

### 4.3 Reskilling & Upskilling
| Kennisgebied | Bronnen | Kerndata |
|-------------|---------|----------|
| Reskilling ROI | WEF Future of Jobs, McKinsey | €5K-15K per medewerker, terugverdientijd 12-18 maanden |
| Effectieve reskilling-methodes | Research + praktijk | On-the-job (70%), peer learning (20%), formeel (10%) — 70-20-10 model |
| Skills taxonomieën | ESCO, O*NET, WEF skills framework | Gestandaardiseerde skills classificatie |
| Sectorale scholingsfondsen | A+O fondsen | Budget, toewijzing, bereik per sector |
| Levenslang Leren cijfers NL | CBS/Eurostat | 26.1% volwassenen in opleiding (EU gemiddelde: 11.9%) |

### 4.4 AI & Automatisering Impact
| Kennisgebied | Bronnen | Kerndata |
|-------------|---------|----------|
| Taakautomatisering per beroep | McKinsey Global Institute, OECD | % taken automatiseerbaar per beroepsgroep |
| GenAI impact op kantoorwerk | McKinsey "The economic potential of GenAI" | 60-70% taken ondersteund, 25-30% overgenomen in kenniswerk |
| AI-adoptiecurves per sector | Gartner, McKinsey | Financieel en ICT voorop, zorg en overheid achter |
| Nieuwe functies door AI | WEF Future of Jobs 2025 | AI trainers, prompt engineers, AI ethici, human-in-the-loop supervisors |
| Productiviteitswinst AI | Diverse studies | 15-40% productiviteitsverhoging in specifieke taken |

### 4.5 Organisatieontwikkeling
| Kennisgebied | Bronnen | Kerndata |
|-------------|---------|----------|
| Reorganisatie-effectiviteit | McKinsey, BCG studies | 70% reorganisaties haalt doelen niet, 5 succesfactoren |
| Change management | Prosci ADKAR, Kotter 8-Step | Bewezen frameworks, slagingspercentages |
| Skills-based organisatie | Deloitte, Mercer | Transitiemodel, 3-5 jaar implementatie |
| Agile transformatie | Spotify model, SAFe | Impact op werkorganisatie en skills |
| Hybride werken | McKinsey, Gartner | Impact op productiviteit, verloop, verzuim |

---

## LAAG 5: Internationale Context & Benchmarks

### 5.1 EU & OECD Vergelijkingsdata
| Bron | URL | NL-relevantie |
|------|-----|---------------|
| Eurostat Employment | ec.europa.eu/eurostat | NL positie in EU: 83.5% werkgelegenheidsgraad (#2) |
| OECD Employment Database | oecd.org/employment | International vergelijkbare metrics |
| OECD Skills Strategy NL | oecd.org | Landenrapport NL skills-beleid |
| EURES | eures.europa.eu | Grensoverschrijdende arbeidsmobiliteit |
| EU Labour Force Survey | Eurostat | Geharmoniseerde arbeidsmarktdata EU27 |

### 5.2 Strategische Rapporten
| Rapport | Uitgever | Kernwaarde |
|---------|----------|------------|
| Future of Jobs 2025 | WEF | Globale skills shift, top-10 skills, banenbalans |
| Global Talent Trends | Mercer | Werkgeversstrategieën, employee experience |
| Human Capital Trends | Deloitte | Jaarlijkse HR-trends, organisatieontwerp |
| Workforce of the Future | PwC | Scenario's voor toekomstige arbeidsmarkt |
| Netherlands Advanced | McKinsey | Specifiek NL: tekorten per sector, productiviteit |
| The Reskilling Revolution | WEF | Kosten en baten van grootschalige reskilling |
| AI and the Future of Work | MIT/Stanford | Academische basis voor AI-impact op werk |

### 5.3 Vergelijkbare Landen
| Land | Vergelijkbaarheid | Kernlessen |
|------|-------------------|------------|
| Duitsland | Vergrijzing, industrie, CAO-structuur | Kurzarbeit, duale opleiding |
| Denemarken | Flexicurity model | Combinatie flexibiliteit + zekerheid |
| Singapore | Skills-based economy | SkillsFuture programma |
| Zweden | Sociaal model, vergrijzing | Activerend arbeidsmarktbeleid |

---

## LAAG 6: Financiële Onderbouwing & Business Case Data

### 6.1 Kostenparameters per Sector
| Parameter | Zorg | ICT | Bouw | Overheid | Retail |
|-----------|------|-----|------|----------|--------|
| Gem. bruto jaarsalaris | €42K | €62K | €45K | €52K | €32K |
| Vervangingskosten factor | 1.5× | 2.0× | 1.2× | 1.3× | 0.8× |
| Cost of vacancy/maand | €4.5K | €8K | €5K | €4K | €2.5K |
| Verzuimkosten/dag | €280 | €400 | €300 | €340 | €210 |
| Gem. time-to-fill (dagen) | 65 | 55 | 45 | 80 | 30 |

**Bronnen:** CBS loonstructuuronderzoek, UWV vacaturedata, sectormonitoren, Randstad/Hays marktrapportages.

### 6.2 ROI Benchmarks voor Interventies
| Interventie | Investering/FTE | Verwachte besparing | ROI | Bron |
|-------------|-----------------|---------------------|-----|------|
| Structured onboarding programma | €2K-5K | 25% verloopreductie | 200-400% | SHRM/Gallup |
| Leiderschapsontwikkeling | €5K-15K | 15% verloop + 10% verzuim reductie | 150-300% | DDI, McKinsey |
| Reskilling programma | €5K-15K | Vermeden vervangingskosten | 180-350% | WEF, Deloitte |
| Verzuimpreventie programma | €1K-3K | 1-2% verzuimreductie | 300-500% | TNO, ArboNed |
| AI-tooling implementatie | €10K-30K | 20-35% productiviteitswinst | 200-400% | McKinsey, Gartner |
| Employer branding | €3K-8K | 30% snellere werving | 150-250% | LinkedIn, Randstad |

### 6.3 Macro-Economische Parameters
| Parameter | Waarde 2026 | Bron |
|-----------|-------------|------|
| Inflatie (CPI) | ~2.5% | CPB |
| Loongroei (CAO) | ~4% | CBS/AWVN |
| Werkloosheid | ~4.0% | CPB |
| BBP-groei | ~1.5% | CPB |
| Minimumloon | ~€2.200/maand | Rijksoverheid |
| Pensioenleeftijd | 67 jaar (stijgend) | SVB |

---

## LAAG 7: Adviesvaardigheid & Communicatie

### 7.1 Strategische Frameworks die de Agent Moet Beheersen
| Framework | Toepassing |
|-----------|-----------|
| Strategic Workforce Planning (SWP) | 5-stappen model: strategie → vraag → aanbod → gap → actie |
| Skills-Based Organization | Transitie van functies naar skills als organiseerprincipe |
| Build-Buy-Borrow-Rent-Bot | 5 opties voor talent gap: opleiden, werven, inhuren, contracteren, automatiseren |
| Total Rewards | Compensatie + benefits + ontwikkeling + werkomgeving + cultuur |
| Employee Experience (EX) | Journey mapping: attract → hire → onboard → develop → retain → exit |
| Workforce Ecosystem | Interne medewerkers + flex + ZZP + partners als integraal systeem |
| Human Capital ROI | Revenue per FTE, profit per FTE, workforce cost ratio |

### 7.2 Gespreksvaardigheden
| Doelgroep | Taal & Focus |
|-----------|-------------|
| CHRO | Strategisch: talent pipeline, cultuur, workforce planning, skills transformatie |
| CFO | Financieel: cost per hire, verzuimkosten, productiviteit/FTE, workforce cost ratio, ROI |
| COO | Operationeel: capaciteit, bezetting, productiviteit, doorlooptijden, quality of hire |
| HR-manager | Tactisch: verzuimbeleid, onboarding, development, compliance |
| Lijnmanager | Praktisch: bezetting, vaardigheden team, succession planning |

### 7.3 NL-Specifieke Consultancy Taal
| Term | Betekenis | Context |
|------|-----------|---------|
| Strategische personeelsplanning (SPP) | NL term voor SWP | Standaard in overheid en zorg |
| Strategische personeelsontwikkeling (SPO) | Focus op ontwikkeling i.p.v. planning | ModellenWerk specialisme |
| Duurzame inzetbaarheid | Langdurige productieve bijdrage | Beleidsprioriteit sinds 2015 |
| Leven lang ontwikkelen | Continuous learning strategie | Overheidsprogramma |
| Sociale innovatie | Innovatie in arbeidsorganisatie | TNO/NCSI gedreven |
| Werkdruk en werkplezier | Balans belasting/belastbaarheid | TNO NEA/WEA framework |

---

## DATABRONNEN: COMPLEET OVERZICHT (48 bronnen)

### Prioriteit 1 — Wekelijks scrapen/ophalen (12 bronnen)
| # | Bron | Type | Format | URL |
|---|------|------|--------|-----|
| 1 | CBS StatLine (arbeidsmarkt) | API | OData/JSON | opendata.cbs.nl |
| 2 | CBS StatLine (verzuim) | API | OData/JSON | opendata.cbs.nl |
| 3 | CBS StatLine (lonen) | API | OData/JSON | opendata.cbs.nl |
| 4 | CBS StatLine (demografie) | API | OData/JSON | opendata.cbs.nl |
| 5 | UWV Spanningsindicator | Dashboard | Web/PDF | uwv.nl |
| 6 | UWV Open Match Data | API | JSON/CSV | data.overheid.nl |
| 7 | UWV Sectorinformatie | Web | HTML/PDF | uwv.nl |
| 8 | ArbeidsmarktInZicht | Dashboard | Web/CSV | arbeidsmarktinzicht.nl |
| 9 | CPB Economische verkenning | Report | PDF | cpb.nl |
| 10 | AZW Info (zorg) | Dashboard | Web/CSV | azwinfo.nl |
| 11 | AWVN CAO-kijker | Dashboard | Web | cao-kijker.awvn.nl |
| 12 | Loonwijzer CAO-database | Database | Web | loonwijzer.nl |

### Prioriteit 2 — Maandelijks ophalen (12 bronnen)
| # | Bron | Type | Format | URL |
|---|------|------|--------|-----|
| 13 | ROA Arbeidsmarktprognoses | Report/Data | Web/PDF | roastatistics.maastrichtuniversity.nl |
| 14 | Techniekpact Monitor | Dashboard | Web/PDF | techniekpactmonitor.nl |
| 15 | EIB Bouw-arbeidsmarkt | Report | PDF | eib.nl |
| 16 | LISA Werkgelegenheid | Data | CSV | lisa.nl |
| 17 | KvK Open Data | API | JSON/CSV | data.overheid.nl |
| 18 | Prognosemodelzw.nl | Interactive | Web | prognosemodelzw.nl |
| 19 | DUO Open Onderwijsdata | Data | CSV | duo.nl |
| 20 | Eurostat Employment | API | REST/JSON | ec.europa.eu/eurostat |
| 21 | OECD Employment Database | API | REST/JSON | stats.oecd.org |
| 22 | TNO Werkstress/NEA | Report | PDF | tno.nl |
| 23 | SER Arbeidsmarktadviezen | Report | PDF | ser.nl |
| 24 | Rijksoverheid Arbeidsmarkt | Policy | HTML/PDF | rijksoverheid.nl |

### Prioriteit 3 — Kwartaal/jaarlijks ophalen (12 bronnen)
| # | Bron | Type | Format | URL |
|---|------|------|--------|-----|
| 25 | ABP Jaarverslag | Report | PDF | abp.nl |
| 26 | PFZW Jaarverslag | Report | PDF | pfzw.nl |
| 27 | McKinsey NL Workforce reports | Report | PDF/Web | mckinsey.com |
| 28 | Deloitte Human Capital Trends NL | Report | PDF | deloitte.nl |
| 29 | WEF Future of Jobs | Report | PDF | weforum.org |
| 30 | Mercer Global Talent Trends | Report | PDF | mercer.com |
| 31 | Randstad Werkmonitor | Report | PDF | randstad.nl |
| 32 | Hays Salarisgids | Report | PDF | hays.nl |
| 33 | Indeed Salarisdata NL | Data | Web | nl.indeed.com |
| 34 | Glassdoor NL | Data | Web | glassdoor.com |
| 35 | SCP Arbeidsmarktrapporten | Report | PDF | scp.nl |
| 36 | RIVM Beroepsziekten | Report | PDF | rivm.nl |

### Prioriteit 4 — Eenmalig + bij update (12 bronnen)
| # | Bron | Type | Format | URL |
|---|------|------|--------|-----|
| 37 | Burgerlijk Wetboek Boek 7 (arbeidsrecht) | Wet | HTML | wetten.overheid.nl |
| 38 | WAB, WWZ, WIA, ZW teksten | Wet | HTML | wetten.overheid.nl |
| 39 | CAO Rijk tekst | CAO | PDF/HTML | caorijk.nl |
| 40 | Sector-CAO's (top-10) | CAO | PDF | loonwijzer.nl + sectorsites |
| 41 | WOR (Ondernemingsraden) | Wet | HTML | wetten.overheid.nl |
| 42 | AI Act (EU verordening) | Wet | PDF/HTML | eur-lex.europa.eu |
| 43 | AVG/GDPR tekst | Wet | PDF/HTML | autoriteitpersoonsgegevens.nl |
| 44 | ESCO Skills Taxonomie | Database | API/CSV | ec.europa.eu/esco |
| 45 | O*NET Occupation Database | Database | API/CSV | onetonline.org |
| 46 | WEF Skills Framework | Framework | PDF | weforum.org |
| 47 | Prosci ADKAR / Kotter | Framework | Web/Book | prosci.com |
| 48 | SHRM Benchmarks | Database | PDF/Web | shrm.org |

---

## UNIEKE DATA DIE NIEMAND ANDERS HEEFT

Dit is de competitive moat van ModellenWerk:

### Eigen Verrijkte Organisatieprofielen
- 40+ organisaties (groeiend met 8/week) met 12-velden steckbrief
- Niet beschikbaar bij CBS, UWV of concurrenten
- Handmatig verrijkt + gevalideerd + AI-geüpdated

### Functiegroep × Organisatie × Sector Matrix
- 200+ functiegroepen met 6 datapunten elk
- Gekoppeld aan specifieke organisaties in specifieke sectoren
- Unieke combinatie van arbeidsmarkt + AI-impact + reskilling per functie

### Business Case Benchmarks
- Kosten van verloop, verzuim, vacatures per sector
- ROI van interventies per type en sector
- Geen publieke bron heeft dit geaggregeerd voor NL

### Klant-Interactiedata (toekomstig)
- Welke risico's zien organisaties als meest urgent?
- Welke business case categorieën hebben de meeste impact?
- Welke interventies worden het vaakst gekozen?

---

## IMPLEMENTATIE: SCHEDULED JOB UITBREIDING

De huidige scheduled job (maandag 07:00) moet uitgebreid met:

1. **CBS API pulls** — 4 datasets wekelijks checken op updates
2. **UWV dashboard scrape** — spanningsindicator + sectorpagina's
3. **CAO-tracking** — AWVN CAO-kijker monitoren voor nieuwe akkoorden
4. **Nieuwsmonitoring** — Google News alerts per sector + "arbeidsmarkt" + "reorganisatie" + "AI adoptie"
5. **Jaarverslag-tracking** — KvK/jaarverslagservice checken voor nieuwe jaarverslagen van tracked organisaties
6. **+8 organisaties/week** — bestaande flow, nu met rijkere bronnen

---

## KWALITEITSPRINCIPES

1. **Altijd bronvermelding** — elke claim heeft een bron + datum
2. **Bandbreedte boven puntschatting** — "verloop 12-18%" is beter dan "verloop 15%"
3. **Actualiteit markeren** — "Q3 2025 data" expliciet benoemen
4. **Onzekerheid erkennen** — confidence levels bij schattingen
5. **Sector-specifiek > generiek** — altijd sectorcontext meegeven
6. **NL-specifiek > internationaal** — Nederlandse data heeft voorrang
7. **Contradictie signaleren** — als bronnen elkaar tegenspreken, beide benoemen

---

*Dit document vormt de basis voor de kennisarchitectuur van de ModellenWerk Workforce Specialist Agent en de training pipeline van The Architect. Versie 1.0 — wordt iteratief uitgebreid op basis van klantinteracties en nieuwe bronnen.*
