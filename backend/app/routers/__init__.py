"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import site as router_site
from app.routers import tower as router_tower
from app.routers import power as router_power
from app.routers import battery as router_battery
from app.routers import genset as router_genset
from app.routers import rectifier as router_rectifier
from app.routers import ac as router_ac
from app.routers import antenna as router_antenna
from app.routers import transmission as router_transmission
from app.routers import feeder as router_feeder
from app.routers import lightningprot as router_lightningprot
from app.routers import firealarm as router_firealarm
from app.routers import dooraccess as router_dooraccess
from app.routers import patrol as router_patrol
from app.routers import fuel as router_fuel
from app.routers import rental as router_rental
from app.routers import electricbill as router_electricbill
from app.routers import demolition as router_demolition
from app.routers import emergency as router_emergency
from app.routers import energyeff as router_energyeff
from app.routers import runtime as router_runtime

ROUTERS = [router_site, router_tower, router_power, router_battery, router_genset, router_rectifier, router_ac, router_antenna, router_transmission, router_feeder, router_lightningprot, router_firealarm, router_dooraccess, router_patrol, router_fuel, router_rental, router_electricbill, router_demolition, router_emergency, router_energyeff, router_runtime]
