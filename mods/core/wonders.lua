-- ROMA AETERNA Lua content file. Edit this file to mod game data.
return {
    {
        id = "pyramids_giza",
        name = "Пирамиды Гизы",
        cost = 260,
        art = "pyramid",
        quote = "«И пирамиды — дела многих и тяжких трудов» — Антипатр Сидонский, эпиграмма о семи чудесах света",
        effects = {
            glory_flat = 80,
            grain_flat = 8
        },
        desc = "+80 славы сразу, +8 зерна/ход | требует: Монументальные комиссии",
        tech = {
            "monument_commissions"
        }
    },
    {
        id = "great_lighthouse",
        name = "Великий маяк Александрии",
        cost = 280,
        art = "harbor",
        quote = "«Плыть необходимо, жить — нет необходимости» — Помпей перед бурей, по свидетельству Плутарха",
        effects = {
            gold_flat = 12,
            navy_power = 2
        },
        desc = "+12 золота/ход, +2 к морскому могуществу | требует: Сеть маяков",
        tech = {
            "lighthouse_network"
        }
    },
    {
        id = "library_alexandria",
        name = "Александрийская библиотека",
        cost = 300,
        art = "library",
        quote = "«Знание есть память о вещах божественных и человеческих» — Ульпиан, Дигесты",
        effects = {
            research_percent = 0.1,
            glory_flat = 60
        },
        desc = "+10% к исследованиям, +60 славы сразу | требует: Латинские библиотеки",
        tech = {
            "latin_libraries"
        }
    },
    {
        id = "colossus_rhodes",
        name = "Колосс Родосский",
        cost = 270,
        art = "statue",
        quote = "«Audentes fortuna iuvat» («Смелым помогает судьба») — Вергилий, Энеида, X.284",
        effects = {
            trade_gold_flat = 10,
            morale_flat = 3
        },
        desc = "+10 золота/ход от торговли, +3 боевой дух | требует: Глубоководные гавани",
        tech = {
            "deepwater_harbors"
        }
    },
    {
        id = "hanging_gardens",
        name = "Висячие сады",
        cost = 260,
        art = "temple",
        quote = "«Чудо висячих садов Вавилона» — Антипатр Сидонский, эпиграмма о семи чудесах света",
        effects = {
            unrest_reduction = 3,
            people_rep_flat = 6
        },
        desc = "−3 к волнениям, +6 к народу сразу | требует: Общественные термы, Монументальные комиссии",
        tech = {
            "public_baths",
            "monument_commissions"
        }
    },
    {
        id = "temple_artemis",
        name = "Храм Артемиды в Эфесе",
        cost = 280,
        art = "temple",
        quote = "«Кровлю вознёсший до туч — всё остальное померкло пред ним» — Антипатр Сидонский о храме Артемиды",
        effects = {
            faith_flat = 5,
            gold_flat = 6
        },
        desc = "+5 веры/ход, +6 золота/ход | требует: Авгурские коллегии",
        tech = {
            "augural_colleges"
        }
    },
    {
        id = "mausoleum_halicarnassus",
        name = "Мавзолей в Галикарнасе",
        cost = 250,
        art = "temple",
        quote = "«Знаю Мавсола гробницу огромную» — Антипатр Сидонский, эпиграмма о семи чудесах света",
        effects = {
            glory_flat = 100
        },
        desc = "+100 славы сразу | требует: Монументальные комиссии",
        tech = {
            "monument_commissions"
        }
    },
    {
        id = "statue_zeus",
        name = "Статуя Зевса Олимпийского",
        cost = 290,
        art = "statue",
        quote = "«Видал Зевса в Олимпии я» — Антипатр Сидонский, эпиграмма о семи чудесах света",
        effects = {
            senate_rep_flat = 5,
            faith_flat = 4
        },
        desc = "+5 к Сенату сразу, +4 веры/ход | требует: Авгурские коллегии",
        tech = {
            "augural_colleges"
        }
    },
    {
        id = "colosseum",
        name = "Колизей",
        cost = 320,
        art = "arena",
        quote = "«Panem et circenses» («Хлеба и зрелищ») — Ювенал, Сатиры, X",
        effects = {
            people_rep_flat = 10,
            unrest_reduction = 4
        },
        desc = "+10 к народу сразу, −4 к волнениям | требует: Великая строительная программа",
        tech = {
            "great_building_program"
        }
    },
    {
        id = "pantheon",
        name = "Пантеон",
        cost = 300,
        art = "temple",
        quote = "«Всё полно богов» — Фалес Милетский, по свидетельству Аристотеля",
        effects = {
            faith_flat = 8,
            unrest_reduction = 2
        },
        desc = "+8 веры/ход, −2 к волнениям | требует: Священный календарь, Opus Caementicium",
        tech = {
            "sacred_calendar",
            "concrete"
        }
    },
    {
        id = "circus_maximus",
        name = "Большой цирк",
        cost = 280,
        art = "arena",
        quote = "«Этот народ... о двух лишь вещах беспокойно мечтает: хлеба и зрелищ» — Ювенал, Сатиры, X",
        effects = {
            people_rep_flat = 8,
            gold_flat = 5
        },
        desc = "+8 к народу сразу, +5 золота/ход | требует: Общественные термы",
        tech = {
            "public_baths"
        }
    },
    {
        id = "aqua_appia",
        name = "Акведук Аппия",
        cost = 240,
        art = "road",
        quote = "Забота о водопроводах касается «не только удобства, но здоровья и даже безопасности Города» — Фронтин, О водопроводах города Рима",
        effects = {
            unrest_reduction = 2,
            grain_flat = 6
        },
        desc = "−2 к волнениям, +6 зерна/ход | требует: Aqua Marcia (акведук)",
        tech = {
            "aqueduct"
        }
    },
    {
        id = "via_appia",
        name = "Аппиева дорога",
        cost = 260,
        art = "road",
        quote = "«Appia... regina viarum» («Аппиева — царица дорог») — Стаций, Сильвы, II",
        effects = {
            gold_flat = 7,
            battle_attack = 1
        },
        desc = "+7 золота/ход, +1 атака армии | требует: Via Appia",
        tech = {
            "via_appia"
        }
    },
    {
        id = "forum_romanum",
        name = "Форум Романум",
        cost = 250,
        art = "temple",
        quote = "«Salus populi suprema lex esto» («Благо народа да будет высшим законом») — Цицерон, О законах, III",
        effects = {
            senate_rep_flat = 6,
            people_rep_flat = 4
        },
        desc = "+6 Сенат, +4 народ сразу | требует: Forum Maximum",
        tech = {
            "forum_maximum"
        }
    },
    {
        id = "curia_julia",
        name = "Курия Юлия",
        cost = 260,
        art = "temple",
        quote = "«Согласием малые государства возрастают, раздором — гибнут даже великие» — Саллюстий, Югуртинская война",
        effects = {
            senate_rep_flat = 10,
            upkeep_percent = -0.04
        },
        desc = "+10 Сенат сразу, −4% содержание | требует: Сенатские комиссии",
        tech = {
            "senatorial_commissions"
        }
    },
    {
        id = "ara_pacis",
        name = "Алтарь Мира",
        cost = 280,
        art = "temple",
        quote = "«Храм Януса Квирина запирают только тогда, когда во всей державе народа римского — и на суше, и на море — стоит мир, добытый победами» — Август, Деяния божественного Августа, XIII",
        effects = {
            unrest_reduction = 5,
            glory_flat = 50
        },
        desc = "−5 к волнениям, +50 славы сразу | требует: Имперский культ",
        tech = {
            "imperial_cult"
        }
    },
    {
        id = "trajan_column",
        name = "Колонна Траяна",
        cost = 310,
        art = "statue",
        quote = "«О дружбе судят по делам, а не по словам» — слова Траяна, по свидетельству Кассия Диона, Римская история, LXVIII",
        effects = {
            battle_attack = 2,
            glory_flat = 70
        },
        desc = "+2 атака армии, +70 славы сразу | требует: Марианская реформа, Монументальные комиссии",
        tech = {
            "marian_reform",
            "monument_commissions"
        }
    },
    {
        id = "baths_caracalla",
        name = "Термы Каракаллы",
        cost = 290,
        art = "temple",
        quote = "«Хочешь мира — готовься к войне» (Si vis pacem, para bellum) — Корнелий Непот / Вегеций",
        effects = {
            people_rep_flat = 7,
            unrest_reduction = 3
        },
        desc = "+7 народ сразу, −3 к волнениям | требует: Общественные термы, Opus Caementicium",
        tech = {
            "public_baths",
            "concrete"
        }
    },
    {
        id = "hadrian_wall",
        name = "Вал Адриана",
        cost = 300,
        art = "wall",
        quote = "«Адриан первым построил стену длиной в восемьдесят миль, чтобы отделить римлян от варваров» — Властелины Августейшего Дома, Жизнь Адриана, 11.2",
        effects = {
            battle_defense = 3,
            barbarian_relation = 5
        },
        desc = "+3 оборона армии, +5 к отношениям с племенами | требует: Limes Romanus",
        tech = {
            "frontier_limes"
        }
    },
    {
        id = "porta_nigra",
        name = "Порта Нигра",
        cost = 230,
        art = "wall",
        quote = "«Необдуманность в битвах... не в обычае римлян... мы же выигрываем сражения своей опытностью и дисциплиной» — Иосиф Флавий, Иудейская война, IV",
        effects = {
            battle_defense = 1,
            gold_flat = 4
        },
        desc = "+1 оборона армии, +4 золота/ход | требует: Opus Caementicium",
        tech = {
            "concrete"
        }
    },
    {
        id = "pont_du_gard",
        name = "Пон-дю-Гар",
        cost = 260,
        art = "road",
        quote = "Должность смотрителя водопроводов касается «не только удобства, но здоровья и даже безопасности Города» — Фронтин, О водопроводах города Рима",
        effects = {
            grain_flat = 7,
            gold_flat = 4
        },
        desc = "+7 зерна/ход, +4 золота/ход | требует: Aqua Marcia (акведук), Opus Caementicium",
        tech = {
            "aqueduct",
            "concrete"
        }
    },
    {
        id = "temple_jupiter",
        name = "Храм Юпитера Капитолийского",
        cost = 300,
        art = "temple",
        quote = "«Caput mundi» («Глава мира») — античное обозначение Рима и его Капитолия",
        effects = {
            senate_rep_flat = 7,
            faith_flat = 6
        },
        desc = "+7 Сенат сразу, +6 веры/ход | требует: Авгурские коллегии",
        tech = {
            "augural_colleges"
        }
    },
    {
        id = "servian_wall",
        name = "Сервиева стена",
        cost = 250,
        art = "wall",
        quote = "«Нельзя считать город неукреплённым, если его оборона зиждется на мужах, а не на кирпичах» — Плутарх приводит слова Ликурга, цит. у Тита Ливия",
        effects = {
            battle_defense = 2,
            unrest_reduction = 1
        },
        desc = "+2 оборона армии, −1 к волнениям | требует: Opus Caementicium",
        tech = {
            "concrete"
        }
    },
    {
        id = "ostia_harbor",
        name = "Порт Остии",
        cost = 270,
        art = "harbor",
        quote = "«Плыть необходимо, жить — нет необходимости» — Помпей перед бурей, по свидетельству Плутарха",
        effects = {
            grain_flat = 10,
            trade_gold_flat = 6
        },
        desc = "+10 зерна/ход, +6 торгового золота/ход | требует: Портовые краны",
        tech = {
            "harbor_cranes"
        }
    },
    {
        id = "capitoline_mint",
        name = "Капитолийский монетный двор",
        cost = 310,
        art = "temple",
        quote = "«Nervus belli pecunia» («Деньги — нерв войны») — Цицерон, Филиппики",
        effects = {
            gold_percent = 0.06
        },
        desc = "+6% ко всему доходу золота | требует: Государственные монетные дворы",
        tech = {
            "state_mints"
        }
    },
    {
        id = "imperial_archives",
        name = "Имперские архивы",
        cost = 260,
        art = "library",
        quote = "«История — свидетельница времён, свет истины, жизнь памяти» — Цицерон, Об ораторе, II.9.36",
        effects = {
            research_percent = 0.06,
            senate_rep_flat = 4
        },
        desc = "+6% к исследованиям, +4 Сенат сразу | требует: Провинциальные архивы, Писцовые бюро",
        tech = {
            "provincial_archives",
            "scribal_bureau"
        }
    },
    {
        id = "school_rhetoric",
        name = "Школа риторов",
        cost = 240,
        art = "library",
        quote = "«В детях редко недостаёт природных способностей; чаще недостаёт попечения об них» — Квинтилиан, Наставления оратору, I.1",
        effects = {
            people_rep_flat = 4,
            senate_rep_flat = 4
        },
        desc = "+4 народ, +4 Сенат сразу | требует: Римские школы",
        tech = {
            "roman_schools"
        }
    },
    {
        id = "castra_praetoria",
        name = "Кастра претория",
        cost = 300,
        art = "wall",
        quote = "«Римский народ подчинил себе вселенную благодаря военным упражнениям и выучке» — Вегеций, Краткое изложение военного дела",
        effects = {
            morale_flat = 5,
            battle_defense = 1
        },
        desc = "+5 боевой дух, +1 оборона армии | требует: Профессиональные центурионы",
        tech = {
            "professional_centurions"
        }
    },
    {
        id = "arsenal_misenum",
        name = "Арсенал Мизена",
        cost = 280,
        art = "harbor",
        quote = "«Плыть необходимо, жить — нет необходимости» — Помпей перед бурей, по свидетельству Плутарха",
        effects = {
            navy_power = 3,
            gold_flat = 5
        },
        desc = "+3 к морскому могуществу, +5 золота/ход | требует: Адмиралтейство",
        tech = {
            "admiralty"
        }
    },
    {
        id = "granaries_egypt",
        name = "Египетские зернохранилища",
        cost = 320,
        art = "pyramid",
        quote = "«Сицилия — кормилица и казначей римского народа» — Цицерон, Вторая речь против Верреса",
        effects = {
            grain_flat = 18
        },
        desc = "+18 зерна/ход | требует: Annona — зерновой флот",
        tech = {
            "grain_fleet"
        }
    },
    {
        id = "temple_mars_ultor",
        name = "Храм Марса Мстителя",
        cost = 300,
        art = "temple",
        quote = "«Хочешь победы — старательно обучай воинов» — Вегеций, Краткое изложение военного дела, III",
        effects = {
            battle_attack = 2,
            morale_flat = 3
        },
        desc = "+2 атака армии, +3 боевой дух | требует: Орлиные штандарты",
        tech = {
            "eagle_standards"
        }
    },
    {
        id = "basilica_aemilia",
        name = "Базилика Эмилия",
        cost = 250,
        art = "temple",
        quote = "«Justitia est constans et perpetua voluntas ius suum cuique tribuendi» («Справедливость — постоянное и неизменное желание воздавать каждому своё») — Ульпиан, Дигесты",
        effects = {
            gold_flat = 6,
            senate_rep_flat = 3
        },
        desc = "+6 золота/ход, +3 Сенат сразу | требует: Канцелярия юристов",
        tech = {
            "jurists_chancery"
        }
    },
    {
        id = "tabularium",
        name = "Табуларий",
        cost = 260,
        art = "library",
        quote = "«Iuris praecepta sunt haec: honeste vivere, alterum non laedere, suum cuique tribuere» («Предписания права суть: честно жить, не вредить другому, каждому воздавать своё») — Ульпиан, Дигесты",
        effects = {
            upkeep_percent = -0.03,
            gold_flat = 4
        },
        desc = "−3% содержание, +4 золота/ход | требует: Писцовые бюро, Сенатские комиссии",
        tech = {
            "scribal_bureau",
            "senatorial_commissions"
        }
    },
    {
        id = "temple_vesta",
        name = "Храм Весты",
        cost = 270,
        art = "temple",
        quote = "Храм Весты, «где горит вечный огонь, а во внутреннем покое хранится залог римской власти» — Тит Ливий, История Рима, XXVI.27",
        effects = {
            faith_flat = 6,
            unrest_reduction = 3
        },
        desc = "+6 веры/ход, −3 к волнениям | требует: Священный календарь",
        tech = {
            "sacred_calendar"
        }
    },
    {
        id = "aqueduct_segovia",
        name = "Акведук Сеговии",
        cost = 280,
        art = "road",
        quote = "«Главное, что пространство вокруг акведука... они занимают постройками или деревьями» — Фронтин, О водопроводах города Рима",
        effects = {
            grain_flat = 8,
            people_rep_flat = 3
        },
        desc = "+8 зерна/ход, +3 народ сразу | требует: Противовесные машины",
        tech = {
            "counterweight_engines"
        }
    },
    {
        id = "amphitheatre_pompeii",
        name = "Амфитеатр Помпей",
        cost = 240,
        art = "arena",
        quote = "«Panem et circenses» («Хлеба и зрелищ») — Ювенал, Сатиры, X",
        effects = {
            people_rep_flat = 5,
            unrest_reduction = 2
        },
        desc = "+5 народ сразу, −2 к волнениям | требует: Общественные термы, Монументальные комиссии",
        tech = {
            "public_baths",
            "monument_commissions"
        }
    },
    {
        id = "limes_germanicus",
        name = "Германский лимес",
        cost = 310,
        art = "wall",
        quote = "«Igitur qui desiderat pacem, praeparet bellum» («Кто желает мира, пусть готовит войну») — Вегеций, Краткое изложение военного дела, III",
        effects = {
            battle_defense = 3,
            barbarian_relation = 4
        },
        desc = "+3 оборона армии, +4 к племенам | требует: Limes Romanus",
        tech = {
            "frontier_limes"
        }
    },
    {
        id = "alexandria_museum",
        name = "Мусейон Александрии",
        cost = 300,
        art = "library",
        quote = "Мусей «имеет место для прогулок, экседру и большой дом, где находится общая столовая для учёных» — Страбон, География, XVII.1.8",
        effects = {
            research_percent = 0.08,
            faith_flat = 3
        },
        desc = "+8% к исследованиям, +3 веры/ход | требует: Александрийская механика",
        tech = {
            "alexandrian_mechanics"
        }
    },
    {
        id = "palatine_palace",
        name = "Палатинский дворец",
        cost = 330,
        art = "temple",
        quote = "«Я нашёл Рим кирпичным, оставляю его вам мраморным» — слова Августа, по свидетельству Светония, Жизнь двенадцати цезарей",
        effects = {
            senate_rep_flat = 5,
            glory_flat = 80,
            gold_percent = 0.03
        },
        desc = "+5 Сенат, +80 славы, +3% золота | требует: Имперский культ, Мраморные карьеры",
        tech = {
            "imperial_cult",
            "marble_quarries"
        }
    },
    {
        id = "constantine_arch",
        name = "Арка Константина",
        cost = 320,
        art = "statue",
        quote = "«Сим знаменем победишь» (ст.-слав. «Сим побѣдиши») — видение Константина, по свидетельству Евсевия Кесарийского, Жизнь Константина, I.28",
        effects = {
            glory_flat = 120,
            morale_flat = 4
        },
        desc = "+120 славы сразу, +4 боевой дух | требует: Pax Romana, Священный календарь",
        tech = {
            "pax_romana",
            "sacred_calendar"
        }
    },
    {
        id = "theatre_marcellus",
        name = "Театр Марцелла",
        cost = 285,
        art = "arena",
        quote = "«Август… построил театр Марцелла во имя своего зятя Марцелла» — Светоний, «Божественный Август», 29",
        effects = {
            people_rep_flat = 6,
            gold_flat = 4
        },
        desc = "+6 народ сразу, +4 золота/ход | требует: Общественные термы",
        tech = {
            "public_baths"
        }
    },
    {
        id = "porticus_octaviae",
        name = "Портик Октавии",
        cost = 270,
        art = "temple",
        quote = "«Он построил… портик Октавии и библиотеку при храме Аполлона» — Светоний, «Божественный Август», 29",
        effects = {
            people_rep_flat = 5,
            science_flat = 1
        },
        desc = "+5 народ сразу, +1 наука/ход | требует: Монументальные комиссии",
        tech = {
            "monument_commissions"
        }
    },
    {
        id = "basilica_ulpia",
        name = "Базилика Ульпия",
        cost = 330,
        art = "temple",
        quote = "«Форум Траяна — сооружение единственное под небом» — Аммиан Марцеллин, «Деяния», XVI.10.15",
        effects = {
            gold_flat = 7,
            senate_rep_flat = 6
        },
        desc = "+7 золота/ход, +6 Сенат | требует: Forum Maximum, Канцелярия юристов",
        tech = {
            "forum_maximum",
            "jurists_chancery"
        }
    },
    {
        id = "markets_trajan",
        name = "Рынки Траяна",
        cost = 320,
        art = "harbor",
        quote = "«Траян построил форум, названный его именем» — Дион Кассий, «Римская история», LXVIII.16",
        effects = {
            gold_flat = 12,
            trade_gold_flat = 4
        },
        desc = "+12 золота/ход, +4 торговое золото | требует: Коллегии торговцев, Портовые краны",
        tech = {
            "merchant_collegia",
            "harbor_cranes"
        }
    },
    {
        id = "campus_martius",
        name = "Марсово поле",
        cost = 300,
        art = "arena",
        quote = "«Поле, посвящённое Марсу, было общим достоянием римского народа» — Тит Ливий, «История Рима», II.5",
        effects = {
            morale_flat = 4,
            battle_attack = 1
        },
        desc = "+4 боевой дух, +1 атака армии | требует: Когортная тактика",
        tech = {
            "cohort_tactics"
        }
    },
    {
        id = "temple_apollo_palatine",
        name = "Храм Аполлона Палатинского",
        cost = 310,
        art = "temple",
        quote = "«Он посвятил храм Аполлону на Палатине и устроил при нём библиотеки» — Светоний, «Божественный Август», 29",
        effects = {
            faith_flat = 5,
            science_flat = 2
        },
        desc = "+5 веры/ход, +2 науки/ход | требует: Авгурские коллегии, Латинские библиотеки",
        tech = {
            "augural_colleges",
            "latin_libraries"
        }
    },
    {
        id = "temple_concordia",
        name = "Храм Согласия",
        cost = 295,
        art = "temple",
        quote = "«Камилл воздвиг храм Согласия, чтобы смягчить распрю между сословиями» — Плутарх, «Камилл», 42",
        effects = {
            senate_rep_flat = 5,
            unrest_reduction = 2
        },
        desc = "+5 Сенат, −2 волнения | требует: Сенатские комиссии",
        tech = {
            "senatorial_commissions"
        }
    },
    {
        id = "temple_saturn_treasury",
        name = "Храм Сатурна и Эрарий",
        cost = 305,
        art = "temple",
        quote = "«Эрарий находится в храме Сатурна» — Варрон, «О латинском языке», V.42",
        effects = {
            gold_flat = 8,
            upkeep_percent = -0.03
        },
        desc = "+8 золота/ход, −3% содержание | требует: Fiscus Imperialis, Государственные монетные дворы",
        tech = {
            "imperial_treasury",
            "state_mints"
        }
    },
    {
        id = "horrea_galbae",
        name = "Склады Гальбы",
        cost = 295,
        art = "harbor",
        quote = "«Horrea Galbae» — «Склады Гальбы», перечень памятников XIII района Рима — Notitia Urbis Romae, Regio XIII",
        effects = {
            grain_flat = 10,
            unrest_reduction = 1
        },
        desc = "+10 зерна/ход, −1 волнения | требует: Государственные амбары, Зерновые контракты",
        tech = {
            "granaries",
            "grain_contracts"
        }
    },
    {
        id = "navalia_rome",
        name = "Navalia — верфи Рима",
        cost = 315,
        art = "ship",
        quote = "«Navalia названы от navis, корабля» — Варрон, «О латинском языке», V.154",
        effects = {
            navy_power = 2,
            gold_flat = 5
        },
        desc = "+2 флот, +5 золота/ход | требует: Квинкверема",
        tech = {
            "naval_quinquereme"
        }
    },
    {
        id = "ravenna_fleet_harbor",
        name = "Гавань флота Равенны",
        cost = 335,
        art = "harbor",
        quote = "«Флот он разместил при Мизене и Равенне, чтобы охранять Верхнее и Нижнее море» — Светоний, «Божественный Август», 49",
        effects = {
            navy_power = 3,
            trade_gold_flat = 4
        },
        desc = "+3 флот, +4 торговое золото | требует: Военно-морские базы, Адмиралтейство",
        tech = {
            "fleet_bases",
            "admiralty"
        }
    },
    {
        id = "forum_iulium",
        name = "Форум Юлия",
        cost = 315,
        art = "temple",
        quote = "«Цезарь построил форум, украсив его храмом Венеры Прародительницы» — Дион Кассий, «Римская история», XLIII.22",
        effects = {
            glory_flat = 75,
            senate_rep_flat = 4
        },
        desc = "+75 славы, +4 Сенат | требует: Forum Maximum, Монументальные комиссии",
        tech = {
            "forum_maximum",
            "monument_commissions"
        }
    },
    {
        id = "temple_venus_genetrix",
        name = "Храм Венеры Прародительницы",
        cost = 305,
        art = "temple",
        quote = "«Он посвятил храм Венере Прародительнице» — Дион Кассий, «Римская история», XLIII.22",
        effects = {
            glory_flat = 70,
            faith_flat = 4
        },
        desc = "+70 славы, +4 веры/ход | требует: Имперский культ",
        tech = {
            "imperial_cult"
        }
    },
    {
        id = "forum_augustum",
        name = "Форум Августа",
        cost = 335,
        art = "temple",
        quote = "«Форум Августа с храмом Марса Мстителя был построен для судов и жеребьёвки провинций» — Светоний, «Божественный Август», 29",
        effects = {
            glory_flat = 90,
            unrest_reduction = 2
        },
        desc = "+90 славы, −2 волнения | требует: Великая строительная программа, Мраморные карьеры",
        tech = {
            "great_building_program",
            "marble_quarries"
        }
    },
    {
        id = "macellum_magnum",
        name = "Большой рынок — Macellum Magnum",
        cost = 300,
        art = "harbor",
        quote = "«Нерон посвятил народу большой рынок — Macellum Magnum» — Дион Кассий, «Римская история», LXI.18",
        effects = {
            gold_flat = 9,
            people_rep_flat = 4
        },
        desc = "+9 золота/ход, +4 народ | требует: Коллегии торговцев, Таможенные посты",
        tech = {
            "merchant_collegia",
            "customs_posts"
        }
    },
    {
        id = "insulae_regulated",
        name = "Регулируемые инсулы",
        cost = 300,
        art = "road",
        quote = "«Дома велено было строить отдельно, без общих стен, с открытыми дворами и портиками» — Тацит, «Анналы», XV.43",
        effects = {
            unrest_reduction = 3,
            people_rep_flat = 4
        },
        desc = "−3 волнения, +4 народ | требует: Городская префектура, Opus Caementicium",
        tech = {
            "urban_prefecture",
            "concrete"
        }
    },
    {
        id = "cloaca_maxima",
        name = "Клоака Максима",
        cost = 310,
        art = "road",
        quote = "«Тарквиний отвёл низины города подземными клоаками» — Тит Ливий, «История Рима», I.56",
        effects = {
            unrest_reduction = 3,
            grain_flat = 4
        },
        desc = "−3 волнения, +4 зерна/ход | требует: Opus Caementicium, Городская префектура",
        tech = {
            "concrete",
            "urban_prefecture"
        }
    },
    {
        id = "aqua_claudia",
        name = "Аква Клавдия",
        cost = 335,
        art = "road",
        quote = "«Аква Клавдия начата Калигулой и завершена Клавдием» — Фронтин, «О водопроводах города Рима», I.13",
        effects = {
            grain_flat = 8,
            people_rep_flat = 5
        },
        desc = "+8 зерна/ход, +5 народ | требует: Aqua Marcia (акведук), Opus Caementicium",
        tech = {
            "aqueduct",
            "concrete"
        }
    },
    {
        id = "aqua_marcia",
        name = "Аква Марция",
        cost = 325,
        art = "road",
        quote = "«Вода Марция славится холодом и чистотой» — Фронтин, «О водопроводах города Рима», I.7",
        effects = {
            unrest_reduction = 2,
            faith_flat = 2,
            people_rep_flat = 4
        },
        desc = "−2 волнения, +2 вера/ход, +4 народ | требует: Aqua Marcia (акведук), Священный календарь",
        tech = {
            "aqueduct",
            "sacred_calendar"
        }
    },
    {
        id = "library_palatine",
        name = "Палатинская библиотека",
        cost = 325,
        art = "library",
        quote = "«Он устроил латинскую и греческую библиотеки при храме Аполлона Палатинского» — Светоний, «Божественный Август», 29",
        effects = {
            science_flat = 4,
            research_percent = 0.04
        },
        desc = "+4 науки/ход, +4% исследований | требует: Латинские библиотеки",
        tech = {
            "latin_libraries"
        }
    },
    {
        id = "athenaeum_hadrian",
        name = "Атеней Адриана",
        cost = 345,
        art = "library",
        quote = "«В Риме Адриан учредил Атеней для свободных искусств» — Аврелий Виктор, «О цезарях», XIV.2",
        effects = {
            science_flat = 5,
            great_person_chance_bonus = 0.03
        },
        desc = "+5 науки/ход, +3% шанс Великих людей | требует: Имперские академии",
        tech = {
            "imperial_academies"
        }
    },
    {
        id = "archimedes_workshop",
        name = "Мастерская Архимеда",
        cost = 360,
        art = "library",
        quote = "«Машины Архимеда поражали римлян огромными камнями и стрелами» — Плутарх, «Марцелл», 14–17",
        effects = {
            artillery_power_percent = 0.12,
            science_flat = 3
        },
        desc = "+12% мощь артиллерии, +3 науки/ход | требует: Александрийская механика",
        tech = {
            "alexandrian_mechanics"
        }
    },
    {
        id = "hero_automata_school",
        name = "Школа автоматов Герона",
        cost = 360,
        art = "library",
        quote = "«Мы излагаем устройства, приводимые в движение воздухом, водой и огнём» — Герон Александрийский, «Пневматика», I, предисловие",
        effects = {
            science_flat = 4,
            artillery_discount = -0.06
        },
        desc = "+4 науки/ход, −6% стоимость артиллерии | требует: Александрийская механика, Повторяющаяся артиллерия",
        tech = {
            "alexandrian_mechanics",
            "repeating_artillery"
        }
    },
    {
        id = "vitruvian_architects_college",
        name = "Коллегия архитекторов Витрувия",
        cost = 340,
        art = "temple",
        quote = "«В архитектуре должны быть прочность, польза и красота» — Витрувий, «Десять книг об архитектуре», I.3.2",
        effects = {
            wonder_discount = -0.06,
            science_flat = 2
        },
        desc = "−6% стоимость чудес, +2 науки/ход | требует: Opus Caementicium, Монументальные комиссии",
        tech = {
            "concrete",
            "monument_commissions"
        }
    },
    {
        id = "imperial_scriptorium",
        name = "Имперский скрипторий",
        cost = 315,
        art = "library",
        quote = "«Август приказал собрать и привести в порядок древние пророческие книги» — Светоний, «Божественный Август», 31",
        effects = {
            science_flat = 4,
            gold_per_province = 1
        },
        desc = "+4 науки/ход, +1 золото за провинцию | требует: Писцовые бюро, Латинские библиотеки",
        tech = {
            "scribal_bureau",
            "latin_libraries"
        }
    },
    {
        id = "praetorium_chancery",
        name = "Преторская канцелярия",
        cost = 320,
        art = "temple",
        quote = "«Право есть искусство доброго и справедливого» — Ульпиан, «Дигесты», I.1.1",
        effects = {
            senate_law_bonus = 2,
            province_unrest_control = 1
        },
        desc = "+2 к законам Сената, +1 контроль волнений | требует: Канцелярия юристов",
        tech = {
            "jurists_chancery"
        }
    },
    {
        id = "augurs_house",
        name = "Дом авгуров",
        cost = 285,
        art = "temple",
        quote = "«У римлян ни одно общественное дело не совершалось без ауспиций» — Цицерон, «О дивинации», I.2",
        effects = {
            faith_flat = 4,
            morale_cap_bonus = 2
        },
        desc = "+4 веры/ход, +2 предел морали | требует: Авгурские коллегии",
        tech = {
            "augural_colleges"
        }
    },
    {
        id = "fasti_capitolini",
        name = "Капитолийские фасты",
        cost = 300,
        art = "temple",
        quote = "«Времена и причины, распределённые по латинскому году, я воспою» — Овидий, «Фасты», I.1",
        effects = {
            faith_flat = 3,
            science_flat = 2,
            unrest_reduction = 1
        },
        desc = "+3 вера/ход, +2 наука/ход, −1 волнения | требует: Священный календарь",
        tech = {
            "sacred_calendar"
        }
    },
    {
        id = "marble_forum_complex",
        name = "Мраморный форум",
        cost = 370,
        art = "temple",
        quote = "«Я принял Рим кирпичным, а оставляю мраморным» — Светоний, «Божественный Август», 28",
        effects = {
            glory_flat = 120,
            wonder_discount = -0.04
        },
        desc = "+120 славы, −4% стоимость чудес | требует: Мраморные карьеры, Великая строительная программа",
        tech = {
            "marble_quarries",
            "great_building_program"
        }
    },
    {
        id = "carrara_imperial_quarries",
        name = "Имперские карьеры Каррары",
        cost = 345,
        art = "road",
        quote = "«В Луне добывают камень белизны и красоты, из которого строят в Риме» — Страбон, «География», V.2.5",
        effects = {
            wonder_discount = -0.08,
            gold_flat = 5
        },
        desc = "−8% стоимость чудес, +5 золота/ход | требует: Мраморные карьеры",
        tech = {
            "marble_quarries"
        }
    },
    {
        id = "prefecture_urbs",
        name = "Префектура Города",
        cost = 330,
        art = "temple",
        quote = "«Август поставил префекта Города, чтобы сдерживать рабов и беспокойных граждан» — Тацит, «Анналы», VI.11",
        effects = {
            unrest_reduction = 4,
            people_rep_flat = 5
        },
        desc = "−4 волнения, +5 народ | требует: Городская префектура",
        tech = {
            "urban_prefecture"
        }
    },
    {
        id = "fire_brigades_vigiles",
        name = "Когорты вигилов",
        cost = 310,
        art = "wall",
        quote = "«Он поставил ночные караулы против пожаров» — Светоний, «Божественный Август», 30",
        effects = {
            unrest_reduction = 3,
            gold_flat = 4
        },
        desc = "−3 волнения, +4 золота/ход | требует: Городская префектура",
        tech = {
            "urban_prefecture"
        }
    },
    {
        id = "milestone_network",
        name = "Сеть мильных камней",
        cost = 300,
        art = "road",
        quote = "«Гай Гракх провёл дороги и поставил камни, отмечающие расстояния» — Плутарх, «Гай Гракх», 7",
        effects = {
            gold_per_province = 1,
            battle_defense = 1
        },
        desc = "+1 золото за провинцию, +1 защита армии | требует: Военные дороги, Cursus Publicus",
        tech = {
            "military_roads",
            "imperial_couriers"
        }
    },
    {
        id = "imperial_post_stations",
        name = "Станции cursus publicus",
        cost = 325,
        art = "road",
        quote = "«На военных дорогах он расставил молодых гонцов, а затем повозки, чтобы быстро получать вести» — Светоний, «Божественный Август», 49",
        effects = {
            gold_percent = 0.03,
            province_unrest_control = 1
        },
        desc = "+3% золота, +1 контроль волнений | требует: Cursus Publicus, Каменные дороги",
        tech = {
            "imperial_couriers",
            "stone_roads"
        }
    },
    {
        id = "universal_citizenship_tablets",
        name = "Таблицы гражданства Каракаллы",
        cost = 350,
        art = "temple",
        quote = "«Антонин сделал всех жителей своей державы римскими гражданами» — Дион Кассий, «Римская история», LXXVIII.9",
        effects = {
            people_rep_flat = 8,
            unrest_reduction = 2,
            gold_percent = 0.02
        },
        desc = "+8 народ, −2 волнения, +2% золота | требует: Всеобщее гражданство, Канцелярия юристов",
        tech = {
            "universal_citizenship",
            "jurists_chancery"
        }
    }
}
