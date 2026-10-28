"""Conservative offline road-trip budgeting, not a live navigation timetable."""
def schedule_roadtrip(order, style, days, close_loop, details=True):
    from .routers.plans import (_haversine_km, ROAD_FACTOR, _pick_stay, _chunk_foods,
                               BIG_KW, FUN_KW)
    from .schedule import recommend_time

    budget = {"轻松": 7.5, "紧凑": 9.0, "亲子": 7.0}.get(style, 7.5)
    drive_cap = {"轻松": 5.0, "紧凑": 6.0, "亲子": 4.5}.get(style, 5.0)
    # A mountain loop must not be estimated at uninterrupted motorway speed.
    mountain = any(any(k in " ".join(s.get('tags') or []) + s['name']
                       for k in ('环线:', '雪山', '草原', '峡谷', '高原')) for s in order)
    speed = 45.0 if mountain else 65.0
    full = []
    current = {"items": [], "spots": [], "used": 0.0, "drive": 0.0, "position": order[0]}

    def clock_span(used, duration):
        def clock(value):
            minute = round((9 + value + (1 if value >= 3 else 0)) * 60)
            return f"{minute // 60:02}:{minute % 60:02}"
        return f"{clock(used)}-{clock(used + duration)}"

    def flush():
        nonlocal current
        if not current["items"]:
            return
        full.append(current)
        current = {"items": [], "spots": [], "used": 0.0, "drive": 0.0,
                   "position": current["position"]}

    def drive(a, b, closing=False):
        hours = _haversine_km(a, b) * ROAD_FACTOR / speed
        if hours < .08:
            current["position"] = b
            return
        # Keep ordinary legs together. Do not send travelers part-way to an unknown
        # overnight stop just to fill the remaining hour after a full-day excursion.
        if current["items"] and (current["used"] + min(hours, drive_cap) > budget or
                                  current["drive"] + min(hours, drive_cap) > drive_cap):
            flush()
        remaining = hours
        while remaining > .001:
            available = min(drive_cap - current["drive"], budget - current["used"])
            if available < .5:
                flush()
                continue
            portion = min(remaining, available)
            arrives = remaining - portion <= .001
            current["items"].append({"spot": f"{'返程' if closing else '转场'}：{a['name']} → {b['name']}",
                "time": clock_span(current["used"], portion),
                "why": f"驾驶约 {portion:.1f} 小时，以导航复核；时间段含必要休息",
                "time_reason": "",
                "duration_h": round(portion, 1), "kind": "transport"})
            current["used"] += portion
            current["drive"] += portion
            current["position"] = b if arrives else None
            remaining -= portion
            if not arrives:
                flush()

    previous = order[0]
    for spot in order:
        if spot.get("id") == -1:
            continue
        if spot is not previous:
            drive(previous, spot)
        text = spot["name"] + " ".join(spot.get("tags") or [])
        slot, reason = recommend_time(spot["name"], spot.get("tags"), spot.get("commercial"))
        big = any(k in text for k in BIG_KW + ("四姑娘", "稻城", "雨崩", "莲宝叶则", "扎尕那"))
        fun = any(k in text for k in FUN_KW)
        hours = 6.0 if big else 1.5 if fun else 2.5
        if current["used"] + hours > budget:
            flush()
        current["items"].append({"spot": spot["name"], "spot_id": spot["id"], "time": clock_span(current["used"], hours),
            "why": f"{spot['city_name']} · 预留约 {hours:g} 小时游览",
            "time_reason": f"参考时段：{slot}；开放时间待确认",
            "duration_h": hours})
        current["used"] += hours
        current["spots"].append(spot)
        current["position"] = spot
        previous = spot
    if close_loop and len(order) >= 2:
        drive(previous, order[0], closing=True)
    flush()
    required = len(full)
    unscheduled = [dict(item) for day in full[days:] for item in day["items"]]
    chosen = full[:days]
    # Spread spare rest days inside the trip instead of padding days after the return.
    spare = max(0, days - len(chosen))
    while spare and chosen:
        index = min(len(chosen) - 1, max(1, len(chosen) // 2))
        position = chosen[index - 1]["position"]
        chosen.insert(index, {"items": [], "spots": [], "used": 0, "drive": 0, "position": position})
        spare -= 1
    daily = []
    for index, day in enumerate(chosen, 1):
        position = day["position"]
        city = position["city_name"] if position else "途中落脚点待确认"
        items = day["items"] or [{"spot": "自由活动 / 休整", "time": "", "why": "保留缓冲，不强行塞满景点"}]
        note = f"驾驶约 {day['drive']:.1f}h · 游览与驾驶合计约 {day['used']:.1f}h（另留餐饮和休息）"
        if position is None:
            note += "；长途已拆日，请出发前按真实导航落实中途住宿，未假定可以当天抵达"
        daily.append({"day": index, "title": f"第{index}天 · {city}", "items": items, "note": note,
                      "driving_hours": round(day["drive"], 2), "activity_hours": round(day["used"], 2),
                      "stay": _pick_stay([position]) if position and details else None,
                      "foods": _chunk_foods(day["spots"]) if details else {}})
    return daily, unscheduled, required, speed
