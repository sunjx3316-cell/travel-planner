# -*- coding: utf-8 -*-
"""景点推荐游玩时段(城市模式的核心算法:时间规划,区别于自驾的路线优化)。

规则基于景点名称/标签/商圈属性,输出 建议时段 + 理由。
时段排序:清晨 < 上午 < 下午 < 傍晚 < 晚上 < 全天。
"""
DAWN = "清晨"
MORNING = "上午"
AFTERNOON = "下午"
SUNSET = "傍晚"
EVENING = "晚上"
FULL = "全天"

SLOT_ORDER = {DAWN: 1, MORNING: 2, AFTERNOON: 3, SUNSET: 4, EVENING: 5, FULL: 6}


def recommend_time(name: str, tags: list = None, commercial: dict = None) -> tuple:
    """返回 (时段, 理由)。规则按优先级排列,名称+标签共同判断。"""
    text = f"{name} {' '.join(tags or [])}"
    # 日出/云海/日照金山:越早越好
    if any(k in text for k in ("日出", "日照金山", "飞来寺", "云海", "观日出")):
        return (DAWN, "日出/云海景观,越早到越值得")
    # 花市:鲜花市场凌晨开市,清晨最新鲜
    if any(k in text for k in ("花市", "花卉市场")):
        return (DAWN, "鲜花市场凌晨开市,清晨花最新鲜,价格也友好")
    # 雪山/冰川/徒步/登山/穿越:大景区,含往返车程需一整天
    if any(k in text for k in ("雪山", "冰川", "徒步", "穿越", "登山", "四姑娘", "稻城", "雨崩")):
        return (FULL, "雪山大景区,含往返车程要一整天,务必尽早出发")
    # 夜景/夜市/美食街/小吃街/步行街/商业街:天黑后
    if any(k in text for k in ("夜市", "美食街", "小吃街", "小吃", "酒吧", "不夜城", "夜景", "灯光",
                               "摩天轮", "夜排档", "夜宵", "夜游", "打铁花", "步行街", "商业街")):
        return (EVENING, "小吃/夜市/步行街,天黑后烟火气最浓")
    # 地标/塔/楼/城墙/广场(按名称判断):半日可逛,傍晚可顺路逛周边夜景
    if any(k in name for k in ("塔", "鼓楼", "钟楼", "楼", "阁", "城墙", "广场", "大桥")):
        return (AFTERNOON, "半日可逛,下午光线好,傍晚可顺路逛周边商圈/夜景")
    # 博物馆/纪念馆/展馆:上午人少
    if any(k in text for k in ("博物馆", "纪念馆", "展览", "科技馆", "美术馆", "故居")):
        return (MORNING, "博物馆上午人少,适合静心参观")
    # 主题乐园/动物园/熊猫基地:全天(开园进)
    if any(k in text for k in ("主题乐园", "乐园", "动物", "熊猫", "迪士尼", "环球")):
        return (FULL, "乐园/动物园建议开园就进,玩一整天")
    # 观景台/日落/九曲:傍晚
    if any(k in text for k in ("九曲", "黄河第一湾", "日落", "夕阳", "观景台")):
        return (SUNSET, "观景/日落时段景色最佳,算好光线时间")
    # 长城/爬山/索道:上午凉快(半日强度)
    if any(k in text for k in ("长城", "爬山", "索道")):
        return (MORNING, "上午凉爽且光线好,避开午后高温与人流")
    # 寺庙/佛/道观:上午清静
    if any(k in text for k in ("寺", "庙", "佛", "道观", "教堂")):
        return (MORNING, "寺庙/教堂上午香客少,氛围清静")
    # 古镇/古城/老街:下午光线好,傍晚还能看夜景
    if any(k in text for k in ("古镇", "古城", "老街", "古街")):
        return (AFTERNOON, "古镇下午光线好,傍晚还可继续看夜景")
    # 溶洞/地下:洞内恒温,上午精力好
    if any(k in text for k in ("溶洞", "地下")):
        return (MORNING, "溶洞恒温,上午精力好,避开排队高峰")
    # 自然山水/公园/湖泊/海滩/草原/湿地/峡谷/山/江河:下午光线好
    if any(k in text for k in ("公园", "湖", "海滩", "草原", "湿地", "峡谷", "山", "江", "河")):
        return (AFTERNOON, "下午光线柔和,适合漫步观景")
    # 商圈:商业/混合下午到晚上,娱乐晚上
    if commercial and commercial.get("type") in ("商业", "混合"):
        return (AFTERNOON, "商圈下午到晚上最热闹,购物+餐饮一条龙")
    if commercial and commercial.get("type") == "娱乐":
        return (EVENING, "娱乐型商圈,晚上人气最旺")
    return (FULL, "全天均可,视体力灵活安排")
