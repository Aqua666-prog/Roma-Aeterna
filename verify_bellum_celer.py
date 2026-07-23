#!/usr/bin/env python3
from __future__ import annotations

import importlib
import os
from pathlib import Path
import py_compile
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
FILES = [
    "roma_resources.py", "roma_army_groups.py", "roma_war_director.py",
    "roma_warfare_ai.py", "roma_aeterna.py",
]

results: list[tuple[str, bool, str]] = []

def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, bool(condition), detail))
    if not condition:
        raise AssertionError(f"{name}: {detail}")

# 1. Syntax
for filename in FILES:
    py_compile.compile(str(ROOT / filename), doraise=True)
check("Python compilation", True, "5 modules")

# 2. Optional test-only technology stub, because the uploaded package does not
# contain the mandatory 100-tech module used by the full game.
stub_dir = Path(tempfile.mkdtemp(prefix="roma_tech_stub_"))
(stub_dir / "roma_technology_overhaul.py").write_text(
    "TECH_TREE={f'tech_{i}':{'name':f'Tech {i}','prereq':[],'category':'administration','cost':10,'effects':{}} for i in range(100)}\n"
    "SCIENCE_TECH_META={k:{'era':1,'category':'administration'} for k in TECH_TREE}\n"
    "SCIENCE_ERA_LABELS={1:'I'}\nTECH_CATEGORY_LABELS={'administration':'Administration'}\n"
    "SCIENCE_CATEGORY_RICH={'administration':'Administration'}\n"
    "TECH_QUOTES={k:{'quote':'Q','author':'A'} for k in TECH_TREE}\n"
    "TECH_UNLOCKED_AUX_UNITS={}\nFLEET_TYPE_ADDITIONS={}\nFLEET_TECH_REQUIREMENTS={}\n"
    "ARTILLERY_REQUIREMENTS={}\nWONDER_REQUIREMENTS={}\nRESOURCE_TECH_RULES={}\n"
    "def validate(): return []\n",
    encoding="utf-8",
)
sys.path.insert(0, str(stub_dir))
sys.path.insert(0, str(ROOT))
ra = importlib.import_module("roma_aeterna")
ag = importlib.import_module("roma_army_groups")
rr = importlib.import_module("roma_resources")
check("Main module import", ra.GAME_VERSION == "4.2.0-bellum-celer", ra.GAME_VERSION)
check("Province roster", len(ra.PROVINCES_DATA) == 44, str(len(ra.PROVINCES_DATA)))
city_count = sum(len(p.get("cities", [])) for p in ra.PROVINCES_DATA)
check("City roster", city_count == 660, str(city_count))

# 3. Conquest rewards and permanent trade route
p = ra.Player("Verifier", "optimates", "normal")
p.gold = 200
p.grain = 100
p.turn = 2
ra.ADVANCED_ECONOMY = None
province = {"name": "Gallia", "wealth": 5, "cities": [{"name": "Lugdunum", "population": 62, "type": "торговый", "difficulty": 5}]}
city = province["cities"][0]
reward = ra.city_conquest_reward(p, province, city, source="army_group_land_assault", announce=False)
check("Large city gold reward", reward["gold"] >= 4000, str(reward["gold"]))
check("Large city grain reward", reward["grain"] >= 120, str(reward["grain"]))
check("Strategic resource loot", bool(reward.get("resources")), str(reward.get("resources")))
wallet_after_reward = p.gold
route = ra.offer_city_trade_route(p, province, city, interactive=False)
check("Immediate city trade route", route.get("built") is True, str(route))
check("Trade route financed by spoils", wallet_after_reward >= route["cost"], f"reward wallet={wallet_after_reward}; cost={route['cost']}")
ra.ensure_v24_state(p)
route_row = p.v24["trade_routes"][0]
check("Route metadata preserved", route_row.get("id") == "city::Gallia::Lugdunum", str(route_row))
check("Passive trade income", ra.v24_trade_income(p) >= route["income"], str(ra.v24_trade_income(p)))
duplicate = ra.city_conquest_reward(p, province, city, announce=False)
check("Reward cannot be claimed twice", duplicate.get("duplicate") and duplicate.get("gold") == 0, str(duplicate))

# 4. Resource bridge
class ResourcePlayer: pass
rp = ResourcePlayer(); rp.turn = 3; rp.metals = {}
applied = rr.grant_resources(rp, {"wheat": 12, "iron": 7, "unknown": 99}, {}, source="test")
check("Resource grant API", applied == {"wheat": 12, "iron": 7}, str(applied))
check("Legacy metals synchronized", rp.metals.get("iron", 0) >= 7, str(rp.metals))
check("Resource invariants", not rr.audit_invariants(rp, {}), str(rr.audit_invariants(rp, {})))

# 5. Legion and auxilia power; auxilia-only armies are legal
class General:
    talent_key = ""
    name = "G"
class Legion:
    def __init__(self, name, quality, strength, morale, veterans=False, elite=False):
        self.name=name; self.quality=quality; self.strength=strength; self.morale=morale
        self.fatigue=0; self.general=General(); self.location="Roma"; self.veterans=veterans; self.elite=elite
class ArmyPlayer: pass
ap = ArmyPlayer(); ap.turn=1
ap.legions=[Legion("Basic",5,50,80), Legion("Elite",10,100,100,True,True)]
ap.aux_units=[{"army_uid":"aux","name":"Elite Aux","strength":100,"attack":45,"defense":40,"morale":100,"xp":45,"veterans":True,"elite":True}]
ap.army_group_system={"schema":2,"version":ag.MODULE_VERSION,"history":[],"settings":{},"next_number":4,"migrated":True,"groups":[
    {"id":"basic","name":"Basic","legions":["Basic"],"auxilia":[],"artillery":{},"fleet_squadrons":[],"doctrine":"balanced","supply":100,"cohesion":100,"fatigue":0,"readiness":100,"command_points":2,"level":1,"upgrades":[]},
    {"id":"elite","name":"Elite","legions":["Elite"],"auxilia":[],"artillery":{},"fleet_squadrons":[],"doctrine":"balanced","supply":100,"cohesion":100,"fatigue":0,"readiness":100,"command_points":2,"level":1,"upgrades":[]},
    {"id":"aux","name":"Aux-only","legions":[],"auxilia":["aux"],"artillery":{},"fleet_squadrons":[],"doctrine":"balanced","supply":100,"cohesion":100,"fatigue":0,"readiness":100,"command_points":2,"level":1,"upgrades":[]},
]}
ctx={"aux_unit_power":lambda u:u["strength"]+u["attack"]+u["defense"]+u.get("xp",0)//2}
basic_power=ag.group_power(ap,"basic",ctx); elite_power=ag.group_power(ap,"elite",ctx); aux_power=ag.group_power(ap,"aux",ctx)
check("Elite legion power", elite_power["land"] > basic_power["land"] * 1.8, f"basic={basic_power['land']}; elite={elite_power['land']}")
check("Auxilia-only combat power", aux_power["land"] > 0 and aux_power["attack"] > 0, str(aux_power))
aux_candidates=[row[0]["id"] for row in ag._province_group_candidates(ap,ap.army_group_system,ctx,"land")]
check("Auxilia-only city assault eligibility", "aux" in aux_candidates, str(aux_candidates))

# 6. Shop tiers
class ScriptedUI:
    def __init__(self, answers): self.answers=list(answers)
    def screen(self): pass
    def header(self,*a,**k): pass
    def info(self,*a,**k): pass
    def table(self,*a,**k): pass
    def wrap(self,*a,**k): pass
    def pause(self,*a,**k): pass
    def choice(self,*a,**k): return self.answers.pop(0)
shop_player=ra.Player("Shop", "optimates", "normal")
shop_player.gold=1_000_000
shop_state=ag.ensure_state(shop_player, vars(ra))
old_pick=ag._pick_assignment_group
old_page=ag._paged_choice
ag._pick_assignment_group=lambda *a,**k: None
try:
    before=len(shop_player.legions)
    ag._shop_legion(ScriptedUI(["3"]), shop_player, shop_state, vars(ra))
    bought=shop_player.legions[-1]
    check("Fully upgraded legion purchase", len(shop_player.legions)==before+1 and bought.quality==10 and bought.strength==100 and bought.morale==100 and bought.veterans and bought.elite, bought.description())

    aux_defs=ra.all_aux_unit_defs()
    if aux_defs:
        shop_player.unlocked_aux_units=[aux_defs[0]["key"]]
        shop_player.metals={k:100000 for k in ra.METAL_TYPES}
        ag._paged_choice=lambda *a,**k: 0
        before_aux=len(shop_player.aux_units)
        ag._shop_auxilia(ScriptedUI(["3"]), shop_player, shop_state, vars(ra))
        bought_aux=shop_player.aux_units[-1]
        check("Fully upgraded auxilia purchase", len(shop_player.aux_units)==before_aux+1 and bought_aux.get("xp",0)>=45 and bought_aux.get("veterans") and bought_aux.get("elite") and bought_aux.get("morale")==100, str(bought_aux))
finally:
    ag._pick_assignment_group=old_pick
    ag._paged_choice=old_page

# 7. Two-victory capture rule with an auxilia-only army
class SilentUI:
    def info(self,*a,**k): pass
    def pause(self,*a,**k): pass
    def screen(self): pass
    def header(self,*a,**k): pass
    def wrap(self,*a,**k): pass
battle_player=ArmyPlayer(); battle_player.turn=1; battle_player.glory=0; battle_player.artillery_supplies=0; battle_player.gold=0; battle_player.grain=0; battle_player.legions=[]
battle_player.aux_units=[{"army_uid":"a1","name":"Aux","strength":45,"attack":15,"defense":14,"morale":80,"xp":0,"veterans":False}]
group={"id":"g","name":"Auxilia","legions":[],"auxilia":["a1"],"artillery":{},"fleet_squadrons":[],"doctrine":"balanced","supply":100,"cohesion":100,"fatigue":0,"readiness":100,"command_points":4,"level":1,"xp":0,"upgrade_points":0,"upgrades":[],"location":"Roma","stance":"ready"}
battle_state={"groups":[group],"province_intel":{},"history":[],"schema":2,"version":ag.MODULE_VERSION,"next_number":2,"migrated":True,"settings":{}}
battle_player.army_group_system=battle_state; battle_player.v24={"fleet":{"sea_zone_control":{},"landing_preparations":{}}}
battle_province={"name":"Test Province","wealth":8,"cities":[{"name":"Test City","difficulty":10,"population":50,"type":"крепость"}]}; battle_city=battle_province["cities"][0]
damage={}; campaigns={}
def get_damage(p,pn,cn): return damage.get((pn,cn),0)
def put_damage(p,pn,cn,amount):
    old=damage.get((pn,cn),0); total=min(100,old+amount); damage[(pn,cn)]=total; return total-old,total,100-total
def next_city(p,pr): return None if battle_city["name"] in campaigns.get(pr["name"],[]) else battle_city
def ensure_campaigns(p): p.city_campaigns=campaigns
battle_ctx={"aux_unit_power":lambda u:u["strength"]+u["attack"]+u["defense"],"next_city_to_attack":next_city,"city_siege_damage":get_damage,"apply_city_siege_damage":put_damage,"city_strength_for_attack":lambda *a:120,"ENEMY_FACTIONS":[],"city_conquest_reward":lambda *a,**k:{"gold":3000,"grain":200,"resources":{"iron":5}},"ensure_city_campaigns":ensure_campaigns,"city_campaign_progress":lambda p,n:(len(campaigns.get(n,[])),1),"offer_city_trade_route":lambda *a,**k:{"built":False},"annex_province_after_campaign":lambda p,pr:(pr,[]),"clear_city_siege_damage":lambda *a:None,"SEA_ZONES":{}}
old_select=ag._select_group_for_province; old_roll=ag._roll_duel; old_apply=ag.apply_battle_result
ag._select_group_for_province=lambda *a,**k:group
ag._roll_duel=lambda ctx,roman,enemy:(roman+5,[3,2],enemy+4,[2,2],1)
ag.apply_battle_result=lambda *a,**k:{}
try:
    ag._execute_province_city_assault(battle_player,battle_province,"land",battle_ctx,SilentUI(),battle_state)
    first=damage.get(("Test Province","Test City"),0)
    check("First successful assault deals at least half", 50 <= first < 100, str(first))
    ag._execute_province_city_assault(battle_player,battle_province,"land",battle_ctx,SilentUI(),battle_state)
    check("Second successful assault captures city", campaigns.get("Test Province")==["Test City"], str(campaigns))
finally:
    ag._select_group_for_province=old_select; ag._roll_duel=old_roll; ag.apply_battle_result=old_apply

print("\nBELLUM CELER verification")
for name, ok, detail in results:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
print(f"\nPassed {sum(ok for _,ok,_ in results)}/{len(results)} checks.")
