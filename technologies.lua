-- ROMA AETERNA Lua content file. Edit this file to mod game data.
return {
    gladius_hispaniensis = {
        name = "Gladius Hispaniensis",
        cost = 50,
        prereq = {},
        category = "military",
        desc = "Испанский меч: +1 к атаке легионов",
        effects = {
            battle_attack = 1
        }
    },
    manipular_drill = {
        name = "Манипулярная муштра",
        cost = 60,
        prereq = {
            "gladius_hispaniensis"
        },
        category = "military",
        desc = "Гибкий строй манипул: +1 атака, +1 защита",
        effects = {
            battle_attack = 1,
            battle_defense = 1
        }
    },
    testudo = {
        name = "Testudo (черепаха)",
        cost = 65,
        prereq = {
            "manipular_drill"
        },
        category = "military",
        desc = "Тактика «черепахи»: +3 защита и тактика №5 в бою",
        effects = {
            battle_defense = 3
        }
    },
    siege_engines = {
        name = "Осадные машины",
        cost = 90,
        prereq = {
            "testudo"
        },
        category = "military",
        desc = "Тараны и баллисты: +6 атака при завоевании провинций",
        effects = {
            battle_siege = 6
        }
    },
    castra_aestiva = {
        name = "Летние лагеря",
        cost = 85,
        prereq = {
            "manipular_drill"
        },
        category = "military",
        desc = "Полевые лагеря: +2 защита, меньше провинциальных волнений",
        effects = {
            battle_defense = 2,
            province_unrest_control = 1
        }
    },
    professional_centurions = {
        name = "Профессиональные центурионы",
        cost = 110,
        prereq = {
            "castra_aestiva",
            "siege_engines"
        },
        category = "military",
        desc = "Центурионы держат строй: +2 атака и -5% содержание легионов",
        effects = {
            battle_attack = 2,
            upkeep_percent = -0.05
        }
    },
    eagle_standards = {
        name = "Орлиные штандарты",
        cost = 120,
        prereq = {
            "professional_centurions"
        },
        category = "military",
        desc = "Aquila поднимает дух: +10 морали и +1 атака",
        effects = {
            battle_attack = 1,
            morale_cap_bonus = 10
        }
    },
    marian_reform = {
        name = "Марианская реформа",
        cost = 150,
        prereq = {
            "eagle_standards"
        },
        category = "military",
        desc = "Профессиональная армия: -10% содержание и +2 атака",
        effects = {
            battle_attack = 2,
            upkeep_percent = -0.1
        }
    },
    ballista_corps = {
        name = "Корпуса баллист",
        cost = 140,
        prereq = {
            "siege_engines"
        },
        category = "military",
        desc = "Тяжёлая артиллерия: +4 осадная атака",
        effects = {
            battle_siege = 4
        }
    },
    frontier_limes = {
        name = "Limes Romanus",
        cost = 160,
        prereq = {
            "castra_aestiva",
            "via_appia"
        },
        category = "military",
        desc = "Пограничная линия: -1 волнений в провинциях и +2 защита",
        effects = {
            battle_defense = 2,
            province_unrest_control = 1
        }
    },
    via_appia = {
        name = "Via Appia",
        cost = 60,
        prereq = {},
        category = "economic",
        desc = "Дороги: +1 золото за провинцию",
        effects = {
            gold_per_province = 1
        }
    },
    currency_reform = {
        name = "Денежная реформа",
        cost = 55,
        prereq = {
            "via_appia"
        },
        category = "economic",
        desc = "Стандартизация денария: -15% содержание легионов",
        effects = {
            upkeep_percent = -0.15
        }
    },
    tax_census = {
        name = "Ценз и налоговые списки",
        cost = 75,
        prereq = {
            "currency_reform"
        },
        category = "economic",
        desc = "Перепись имущества: +1 золото за провинцию",
        effects = {
            gold_per_province = 1
        }
    },
    banking = {
        name = "Банковское дело",
        cost = 85,
        prereq = {
            "currency_reform"
        },
        category = "economic",
        desc = "Менялы и кредиторы: +10% дохода золота",
        effects = {
            gold_percent = 0.1
        }
    },
    latifundia = {
        name = "Латифундии",
        cost = 100,
        prereq = {
            "tax_census"
        },
        category = "economic",
        desc = "Крупные хозяйства: +25 золота/ход",
        effects = {
            gold_flat = 25
        }
    },
    merchant_collegia = {
        name = "Коллегии торговцев",
        cost = 95,
        prereq = {
            "banking"
        },
        category = "economic",
        desc = "Торговые корпорации: +15 золота/ход",
        effects = {
            gold_flat = 15
        }
    },
    customs_posts = {
        name = "Таможенные посты",
        cost = 110,
        prereq = {
            "merchant_collegia"
        },
        category = "economic",
        desc = "Пошлины на дорогах и портах: +2 золота за провинцию",
        effects = {
            gold_per_province = 2
        }
    },
    state_mints = {
        name = "Государственные монетные дворы",
        cost = 130,
        prereq = {
            "banking",
            "tax_census"
        },
        category = "economic",
        desc = "Контроль чеканки: +8% дохода золота",
        effects = {
            gold_percent = 0.08
        }
    },
    grain_contracts = {
        name = "Зерновые контракты",
        cost = 120,
        prereq = {
            "latifundia"
        },
        category = "economic",
        desc = "Поставки хлеба: +20 зерна/ход",
        effects = {
            grain_flat = 20
        }
    },
    imperial_treasury = {
        name = "Fiscus Imperialis",
        cost = 170,
        prereq = {
            "state_mints",
            "customs_posts"
        },
        category = "economic",
        desc = "Имперская казна: +12% дохода золота и +30 золота/ход",
        effects = {
            gold_percent = 0.12,
            gold_flat = 30
        }
    },
    aqueduct = {
        name = "Aqua Marcia (акведук)",
        cost = 70,
        prereq = {
            "via_appia"
        },
        category = "civil",
        desc = "Акведук: -10 базовых волнений, +10 зерна/ход",
        effects = {
            unrest_reduction = 10,
            grain_flat = 10
        }
    },
    concrete = {
        name = "Opus Caementicium",
        cost = 85,
        prereq = {
            "aqueduct"
        },
        category = "civil",
        desc = "Римский бетон: укрепления дешевле и +1 защита",
        effects = {
            garrison_discount = 0.1,
            battle_defense = 1
        }
    },
    public_baths = {
        name = "Общественные термы",
        cost = 95,
        prereq = {
            "aqueduct"
        },
        category = "civil",
        desc = "Термы успокаивают городскую толпу: -5 волнений",
        effects = {
            unrest_reduction = 5
        }
    },
    forum_maximum = {
        name = "Forum Maximum",
        cost = 80,
        prereq = {
            "aqueduct"
        },
        category = "civil",
        desc = "Главный форум: +5 репутации Сената за закон",
        effects = {
            senate_law_bonus = 5
        }
    },
    granaries = {
        name = "Государственные амбары",
        cost = 90,
        prereq = {
            "aqueduct"
        },
        category = "civil",
        desc = "Запасы зерна: +15 зерна/ход",
        effects = {
            grain_flat = 15
        }
    },
    stone_roads = {
        name = "Каменные дороги",
        cost = 105,
        prereq = {
            "via_appia",
            "concrete"
        },
        category = "civil",
        desc = "Мощёные дороги: +1 золото за провинцию, -1 провинциальных волнений",
        effects = {
            gold_per_province = 1,
            province_unrest_control = 1
        }
    },
    harbor_cranes = {
        name = "Портовые краны",
        cost = 115,
        prereq = {
            "concrete",
            "naval_quinquereme"
        },
        category = "civil",
        desc = "Портовая механизация: +12 золота и +10 зерна/ход",
        effects = {
            gold_flat = 12,
            grain_flat = 10
        }
    },
    military_roads = {
        name = "Военные дороги",
        cost = 125,
        prereq = {
            "stone_roads",
            "castra_aestiva"
        },
        category = "civil",
        desc = "Маршевые трассы: +2 атака и +1 защита",
        effects = {
            battle_attack = 2,
            battle_defense = 1
        }
    },
    provincial_archives = {
        name = "Провинциальные архивы",
        cost = 135,
        prereq = {
            "forum_maximum",
            "tax_census"
        },
        category = "civil",
        desc = "Документы и кадастры: романизация дешевле, наместники лояльнее",
        effects = {
            romanization_discount = 0.15,
            governor_loyalty_bonus = 1
        }
    },
    great_building_program = {
        name = "Великая строительная программа",
        cost = 180,
        prereq = {
            "provincial_archives",
            "harbor_cranes"
        },
        category = "civil",
        desc = "Монументальное строительство: +20 славы за ход и -5 волнений",
        effects = {
            glory_per_turn = 20,
            unrest_reduction = 5
        }
    },
    naval_quinquereme = {
        name = "Квинкверема",
        cost = 75,
        prereq = {
            "gladius_hispaniensis"
        },
        category = "naval",
        desc = "Военный флот: +2 защита от набегов и морских войн",
        effects = {
            battle_defense = 2
        }
    },
    corvus_bridge = {
        name = "Corvus",
        cost = 85,
        prereq = {
            "naval_quinquereme"
        },
        category = "naval",
        desc = "Абордажный мостик: +2 атака",
        effects = {
            battle_attack = 2
        }
    },
    naval_supply = {
        name = "Морское снабжение",
        cost = 100,
        prereq = {
            "naval_quinquereme",
            "grain_contracts"
        },
        category = "naval",
        desc = "Флот снабжения: -2 зерна содержания армии и +10 зерна/ход",
        effects = {
            grain_flat = 10,
            grain_upkeep_flat = -2
        }
    },
    admiralty = {
        name = "Адмиралтейство",
        cost = 120,
        prereq = {
            "corvus_bridge"
        },
        category = "naval",
        desc = "Управление флотом: +1 атака и +1 защита",
        effects = {
            battle_attack = 1,
            battle_defense = 1
        }
    },
    pirate_suppression = {
        name = "Подавление пиратов",
        cost = 115,
        prereq = {
            "admiralty"
        },
        category = "naval",
        desc = "Чистое море: +15 золота/ход",
        effects = {
            gold_flat = 15
        }
    },
    mare_nostrum = {
        name = "Mare Nostrum",
        cost = 155,
        prereq = {
            "pirate_suppression",
            "harbor_cranes"
        },
        category = "naval",
        desc = "Средиземное море наше: +2 золота за провинцию и +2 атака",
        effects = {
            gold_per_province = 2,
            battle_attack = 2
        }
    },
    fleet_bases = {
        name = "Военно-морские базы",
        cost = 130,
        prereq = {
            "naval_supply"
        },
        category = "naval",
        desc = "Базы флота: +2 защита, гарнизоны дешевле",
        effects = {
            battle_defense = 2,
            garrison_discount = 0.1
        }
    },
    grain_fleet = {
        name = "Annona — зерновой флот",
        cost = 145,
        prereq = {
            "fleet_bases",
            "granaries"
        },
        category = "naval",
        desc = "Египетский хлеб: +30 зерна/ход",
        effects = {
            grain_flat = 30
        }
    },
    lighthouse_network = {
        name = "Сеть маяков",
        cost = 135,
        prereq = {
            "fleet_bases"
        },
        category = "naval",
        desc = "Маяки и сигналы: +10 золота, +10 зерна",
        effects = {
            gold_flat = 10,
            grain_flat = 10
        }
    },
    deepwater_harbors = {
        name = "Глубоководные гавани",
        cost = 165,
        prereq = {
            "lighthouse_network",
            "mare_nostrum"
        },
        category = "naval",
        desc = "Большие гавани: +10% золота и +20 зерна",
        effects = {
            gold_percent = 0.1,
            grain_flat = 20
        }
    },
    twelve_tables = {
        name = "Законы XII таблиц",
        cost = 65,
        prereq = {},
        category = "administration",
        desc = "Писаное право: -5 волнений",
        effects = {
            unrest_reduction = 5
        }
    },
    provincial_law = {
        name = "Провинциальное право",
        cost = 90,
        prereq = {
            "twelve_tables"
        },
        category = "administration",
        desc = "Правовые формулы для провинций: романизация дешевле",
        effects = {
            romanization_discount = 0.1
        }
    },
    citizenship_grants = {
        name = "Дарование гражданства",
        cost = 110,
        prereq = {
            "provincial_law"
        },
        category = "administration",
        desc = "Муниципальная элита получает статус: +2 золота за провинцию",
        effects = {
            gold_per_province = 2
        }
    },
    governor_audits = {
        name = "Проверки наместников",
        cost = 105,
        prereq = {
            "provincial_archives"
        },
        category = "administration",
        desc = "Контроль коррупции: наместники теряют меньше лояльности",
        effects = {
            governor_loyalty_bonus = 1,
            province_unrest_control = 1
        }
    },
    imperial_couriers = {
        name = "Cursus Publicus",
        cost = 125,
        prereq = {
            "stone_roads",
            "provincial_law"
        },
        category = "administration",
        desc = "Имперская почта: +1 золото за провинцию, +1 защита",
        effects = {
            gold_per_province = 1,
            battle_defense = 1
        }
    },
    roman_schools = {
        name = "Римские школы",
        cost = 115,
        prereq = {
            "citizenship_grants"
        },
        category = "administration",
        desc = "Латинская paideia: романизация дешевле и -5 волнений",
        effects = {
            romanization_discount = 0.1,
            unrest_reduction = 5
        }
    },
    senatorial_commissions = {
        name = "Сенатские комиссии",
        cost = 125,
        prereq = {
            "governor_audits",
            "forum_maximum"
        },
        category = "administration",
        desc = "Комиссии Сената: +5 к бонусу за законы",
        effects = {
            senate_law_bonus = 5
        }
    },
    imperial_cult = {
        name = "Имперский культ",
        cost = 140,
        prereq = {
            "roman_schools",
            "great_building_program"
        },
        category = "administration",
        desc = "Культ Рима и власти: +15 славы/ход, -5 волнений",
        effects = {
            glory_per_turn = 15,
            unrest_reduction = 5
        }
    },
    universal_citizenship = {
        name = "Всеобщее гражданство",
        cost = 170,
        prereq = {
            "imperial_cult",
            "citizenship_grants"
        },
        category = "administration",
        desc = "Все свободные жители — граждане: +10% дохода",
        effects = {
            gold_percent = 0.1
        }
    },
    pax_romana = {
        name = "Pax Romana",
        cost = 220,
        prereq = {
            "universal_citizenship",
            "imperial_treasury",
            "mare_nostrum",
            "marian_reform"
        },
        category = "administration",
        desc = "Высшая имперская стабильность: +25 славы/ход, -10 волнений, +10% золота",
        effects = {
            glory_per_turn = 25,
            unrest_reduction = 10,
            gold_percent = 0.1
        }
    },
    iron_armories = {
        name = "Государственные оружейные",
        cost = 90,
        prereq = {
            "gladius_hispaniensis"
        },
        category = "military",
        desc = "Оружейные мастерские снабжают легионы и открывают бронированные ауксилии.",
        effects = {
            battle_attack = 1,
            aux_training_bonus = 1
        }
    },
    pila_mass_production = {
        name = "Массовое производство пилумов",
        cost = 100,
        prereq = {
            "iron_armories"
        },
        category = "military",
        desc = "Пилумы становятся штатным оружием: сильнее первый удар легионов.",
        effects = {
            battle_attack = 1
        }
    },
    cohort_tactics = {
        name = "Когортная тактика",
        cost = 120,
        prereq = {
            "manipular_drill",
            "pila_mass_production"
        },
        category = "military",
        desc = "Когорты дают легиону плотность, резерв и устойчивость.",
        effects = {
            battle_attack = 1,
            battle_defense = 2
        }
    },
    field_medicine = {
        name = "Полевая медицина",
        cost = 110,
        prereq = {
            "castra_aestiva"
        },
        category = "military",
        desc = "Военные врачи и перевязочные пункты уменьшают цену победы.",
        effects = {
            army_loss_reduction = 0.08
        }
    },
    veteran_colonies = {
        name = "Ветеранские колонии",
        cost = 125,
        prereq = {
            "marian_reform"
        },
        category = "administration",
        desc = "Ветераны получают землю и превращают границу в римскую опору.",
        effects = {
            unrest_reduction = 1,
            glory_per_turn = 1
        }
    },
    auxiliary_recruitment = {
        name = "Штатная вербовка ауксилий",
        cost = 115,
        prereq = {
            "citizenship_grants"
        },
        category = "military",
        desc = "Провинциальные отряды становятся частью регулярной армии.",
        effects = {
            aux_training_bonus = 2,
            battle_defense = 1
        }
    },
    siege_doctrine = {
        name = "Осадная доктрина",
        cost = 115,
        prereq = {
            "siege_engines"
        },
        category = "military",
        desc = "Осада превращается из ярости в расчёт.",
        effects = {
            battle_siege = 2
        }
    },
    torsion_artillery = {
        name = "Торсионная артиллерия",
        cost = 135,
        prereq = {
            "siege_doctrine",
            "iron_armories"
        },
        category = "engineering",
        desc = "Баллисты и скорпионы усиливают полевые и осадные армии.",
        effects = {
            battle_siege = 2,
            artillery_power_percent = 0.08
        }
    },
    legionary_workshops = {
        name = "Легионные мастерские",
        cost = 125,
        prereq = {
            "castra_aestiva",
            "iron_armories"
        },
        category = "engineering",
        desc = "Fabri чинят оружие, машины и дороги прямо в походе.",
        effects = {
            battle_siege = 1,
            artillery_discount = -0.05
        }
    },
    counterweight_engines = {
        name = "Противовесные машины",
        cost = 155,
        prereq = {
            "torsion_artillery",
            "harbor_cranes"
        },
        category = "engineering",
        desc = "Тяжёлые метательные машины ломают стены быстрее.",
        effects = {
            battle_siege = 3,
            artillery_power_percent = 0.1
        }
    },
    incendiary_munitions = {
        name = "Зажигательные боеприпасы",
        cost = 145,
        prereq = {
            "torsion_artillery"
        },
        category = "engineering",
        desc = "Смола, сера и огненные снаряды помогают против башен и лагерей.",
        effects = {
            battle_siege = 2,
            artillery_power_percent = 0.06
        }
    },
    mobile_field_artillery = {
        name = "Мобильная полевая артиллерия",
        cost = 160,
        prereq = {
            "legionary_workshops",
            "torsion_artillery"
        },
        category = "engineering",
        desc = "Скорпионы и лёгкие баллисты идут вместе с легионом.",
        effects = {
            battle_attack = 1,
            battle_siege = 2
        }
    },
    repeating_artillery = {
        name = "Повторяющаяся артиллерия",
        cost = 190,
        prereq = {
            "alexandrian_mechanics",
            "mobile_field_artillery"
        },
        category = "engineering",
        desc = "Полиболы дают поздней армии плотный механический огонь.",
        effects = {
            battle_attack = 2,
            battle_siege = 3,
            artillery_power_percent = 0.12
        }
    },
    naval_artillery = {
        name = "Корабельная артиллерия",
        cost = 150,
        prereq = {
            "admiralty",
            "torsion_artillery"
        },
        category = "naval",
        desc = "Катапульты и скорпионы превращают корабль в крепость.",
        effects = {
            navy_power = 2,
            battle_siege = 1
        }
    },
    scribal_bureau = {
        name = "Писцовые бюро",
        cost = 90,
        prereq = {
            "tax_census"
        },
        category = "administration",
        desc = "Писцы, архивы и реестры ускоряют управление державой.",
        effects = {
            science_flat = 2,
            gold_per_province = 1
        }
    },
    latin_libraries = {
        name = "Латинские библиотеки",
        cost = 110,
        prereq = {
            "roman_schools",
            "scribal_bureau"
        },
        category = "science",
        desc = "Библиотеки хранят память и ускоряют исследования.",
        effects = {
            science_flat = 3,
            research_percent = 0.05
        }
    },
    greek_tutors = {
        name = "Греческие наставники",
        cost = 100,
        prereq = {
            "roman_schools"
        },
        category = "science",
        desc = "Греческая paideia усиливает римскую элиту.",
        effects = {
            research_percent = 0.05,
            great_person_chance_bonus = 0.02
        }
    },
    alexandrian_mechanics = {
        name = "Александрийская механика",
        cost = 170,
        prereq = {
            "greek_tutors",
            "harbor_cranes"
        },
        category = "science",
        desc = "Школа механиков открывает сложные машины и инженерные чудеса.",
        effects = {
            science_flat = 4,
            artillery_power_percent = 0.08
        }
    },
    imperial_academies = {
        name = "Имперские академии",
        cost = 180,
        prereq = {
            "latin_libraries",
            "greek_tutors"
        },
        category = "science",
        desc = "Академии готовят юристов, врачей, инженеров и чиновников.",
        effects = {
            research_percent = 0.08,
            great_person_chance_bonus = 0.03
        }
    },
    jurists_chancery = {
        name = "Канцелярия юристов",
        cost = 120,
        prereq = {
            "twelve_tables",
            "scribal_bureau"
        },
        category = "administration",
        desc = "Responsa юристов превращают управление в систему права.",
        effects = {
            senate_law_bonus = 2,
            province_unrest_control = 1
        }
    },
    augural_colleges = {
        name = "Авгурские коллегии",
        cost = 95,
        prereq = {
            "twelve_tables"
        },
        category = "religion",
        desc = "Священные коллегии укрепляют легитимность решений.",
        effects = {
            faith_flat = 2,
            morale_cap_bonus = 2
        }
    },
    sacred_calendar = {
        name = "Священный календарь",
        cost = 105,
        prereq = {
            "augural_colleges"
        },
        category = "religion",
        desc = "Fasti упорядочивают праздники, суды, войны и ритуалы.",
        effects = {
            faith_flat = 3,
            unrest_reduction = 1
        }
    },
    monument_commissions = {
        name = "Монументальные комиссии",
        cost = 130,
        prereq = {
            "forum_maximum",
            "concrete"
        },
        category = "engineering",
        desc = "Государство строит храмы, арки, колонны и зрелищные комплексы.",
        effects = {
            wonder_discount = -0.05,
            glory_per_turn = 1
        }
    },
    marble_quarries = {
        name = "Мраморные карьеры",
        cost = 145,
        prereq = {
            "stone_roads",
            "monument_commissions"
        },
        category = "engineering",
        desc = "Каррарский мрамор удешевляет великие стройки.",
        effects = {
            wonder_discount = -0.08,
            glory_per_turn = 1
        }
    },
    urban_prefecture = {
        name = "Городская префектура",
        cost = 135,
        prereq = {
            "imperial_couriers",
            "granaries"
        },
        category = "administration",
        desc = "Префект города следит за порядком, хлебом и инфраструктурой.",
        effects = {
            unrest_reduction = 2,
            people_rep_flat = 3
        }
    }
}
