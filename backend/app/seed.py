# -*- coding: utf-8 -*-
"""种子数据:10 个热门城市 + 景区 + 少量示例笔记(is_sample=1)。

示例笔记用于在未接入小红书采集时演示 AI 加工管线:
- guide: 攻略(有具体细节的正常攻略 / 通篇溢美的疑似暗广)
- avoid: 避雷(具体事实型 / 情绪发泄型尬黑)
- mixed: 中立混合

正式数据将由 backend/collector/xhs_collector.py 采集后入库。
"""
import json
import sqlite3
from datetime import datetime


def _norm_province(p: str) -> str:
    """省·州 → 省:环线/4A 数据把「甘肃省·甘南州」式写法归一化为「甘肃省」。"""
    return (p or "").split("·")[0]

CITIES = [
    {"name": "北京", "province": "北京市", "lng": 116.407, "lat": 39.904},
    {"name": "上海", "province": "上海市", "lng": 121.474, "lat": 31.230},
    {"name": "广州", "province": "广东省", "lng": 113.264, "lat": 23.129},
    {"name": "成都", "province": "四川省", "lng": 104.066, "lat": 30.573},
    {"name": "重庆", "province": "重庆市", "lng": 106.551, "lat": 29.563},
    {"name": "西安", "province": "陕西省", "lng": 108.940, "lat": 34.341},
    {"name": "杭州", "province": "浙江省", "lng": 120.155, "lat": 30.274},
    {"name": "三亚", "province": "海南省", "lng": 109.512, "lat": 18.253},
    {"name": "丽江", "province": "云南省", "lng": 100.228, "lat": 26.855},
    {"name": "长沙", "province": "湖南省", "lng": 112.939, "lat": 28.228},
]

SPOTS = {
    "北京": [
        {"name": "故宫博物院", "rating": 4.9, "address": "东城区景山前街4号", "tags": ["历史", "博物馆"]},
        {"name": "颐和园", "rating": 4.8, "address": "海淀区新建宫门路19号", "tags": ["园林", "湖泊"]},
        {"name": "八达岭长城", "rating": 4.7, "address": "延庆区G6京藏高速58号出口", "tags": ["历史", "登山"]},
        {"name": "天坛公园", "rating": 4.7, "address": "东城区天坛东里甲1号", "tags": ["历史", "公园"]},
        {"name": "北京环球影城", "rating": 4.6, "address": "通州区京哈高速与东六环交汇处", "tags": ["主题乐园"]},
    ],
    "上海": [
        {"name": "外滩", "rating": 4.8, "address": "黄浦区中山东一路", "tags": ["城市", "夜景"]},
        {"name": "上海迪士尼乐园", "rating": 4.8, "address": "浦东新区川沙新镇", "tags": ["主题乐园"]},
        {"name": "豫园", "rating": 4.6, "address": "黄浦区福佑路168号", "tags": ["园林", "历史"]},
        {"name": "武康路", "rating": 4.5, "address": "徐汇区武康路", "tags": ["街区", "拍照"]},
    ],
    "广州": [
        {"name": "广州塔", "rating": 4.7, "address": "海珠区阅江西路222号", "tags": ["地标", "夜景"]},
        {"name": "长隆野生动物世界", "rating": 4.8, "address": "番禺区汉溪大道东299号", "tags": ["动物园", "亲子"]},
        {"name": "沙面", "rating": 4.6, "address": "荔湾区沙面北街", "tags": ["历史", "街区"]},
        {"name": "陈家祠", "rating": 4.6, "address": "荔湾区中山七路恩龙里34号", "tags": ["历史", "建筑"]},
    ],
    "成都": [
        {"name": "宽窄巷子", "rating": 4.5, "address": "青羊区长顺街附近", "tags": ["街区", "美食"]},
        {"name": "成都大熊猫繁育研究基地", "rating": 4.9, "address": "成华区熊猫大道1375号", "tags": ["动物", "亲子"]},
        {"name": "都江堰", "rating": 4.8, "address": "都江堰市公园路", "tags": ["水利", "历史"]},
        {"name": "锦里古街", "rating": 4.4, "address": "武侯区武侯祠大街231号", "tags": ["街区", "美食"]},
    ],
    "重庆": [
        {"name": "洪崖洞", "rating": 4.6, "address": "渝中区嘉陵江滨江路88号", "tags": ["夜景", "地标"]},
        {"name": "磁器口古镇", "rating": 4.4, "address": "沙坪坝区磁南街1号", "tags": ["古镇", "美食"]},
        {"name": "长江索道", "rating": 4.5, "address": "渝中区新华路151号", "tags": ["交通", "体验"]},
        {"name": "武隆天生三桥", "rating": 4.8, "address": "武隆区仙女山镇", "tags": ["自然", "喀斯特"]},
    ],
    "西安": [
        {"name": "秦始皇兵马俑博物馆", "rating": 4.9, "address": "临潼区秦陵北路", "tags": ["历史", "博物馆"]},
        {"name": "大雁塔", "rating": 4.6, "address": "雁塔区雁塔南路", "tags": ["历史", "佛教"]},
        {"name": "大唐不夜城", "rating": 4.6, "address": "雁塔区慈恩路", "tags": ["街区", "夜景"]},
        {"name": "西安城墙", "rating": 4.7, "address": "碑林区南大街", "tags": ["历史", "骑行"]},
    ],
    "杭州": [
        {"name": "西湖", "rating": 4.9, "address": "西湖区龙井路1号", "tags": ["湖泊", "免费"]},
        {"name": "灵隐寺", "rating": 4.7, "address": "西湖区灵隐路法云弄1号", "tags": ["佛教", "山林"]},
        {"name": "千岛湖", "rating": 4.7, "address": "淳安县千岛湖镇", "tags": ["湖泊", "度假"]},
        {"name": "西溪国家湿地公园", "rating": 4.5, "address": "西湖区天目山路518号", "tags": ["湿地", "自然"]},
    ],
    "三亚": [
        {"name": "亚龙湾", "rating": 4.8, "address": "吉阳区亚龙湾路", "tags": ["海滩", "度假"]},
        {"name": "蜈支洲岛", "rating": 4.7, "address": "海棠区后海村", "tags": ["海岛", "潜水"]},
        {"name": "天涯海角", "rating": 4.3, "address": "天涯区天涯镇", "tags": ["地标", "海滩"]},
        {"name": "南山文化旅游区", "rating": 4.7, "address": "崖州区南山", "tags": ["佛教", "祈福"]},
    ],
    "丽江": [
        {"name": "丽江古城", "rating": 4.6, "address": "古城区大研镇", "tags": ["古城", "夜景"]},
        {"name": "玉龙雪山", "rating": 4.8, "address": "玉龙纳西族自治县", "tags": ["雪山", "自然"]},
        {"name": "泸沽湖", "rating": 4.8, "address": "宁蒗彝族自治县", "tags": ["湖泊", "自然"]},
        {"name": "束河古镇", "rating": 4.5, "address": "古城区束河路", "tags": ["古镇", "安静"]},
    ],
    "长沙": [
        {"name": "岳麓山", "rating": 4.7, "address": "岳麓区登高路58号", "tags": ["山林", "免费"]},
        {"name": "橘子洲", "rating": 4.7, "address": "岳麓区橘子洲头2号", "tags": ["公园", "地标"]},
        {"name": "湖南省博物馆", "rating": 4.8, "address": "开福区东风路50号", "tags": ["博物馆", "历史"]},
        {"name": "太平街", "rating": 4.3, "address": "天心区太平街", "tags": ["街区", "美食"]},
    ],
}

# 示例笔记:spot 名 -> 笔记列表(标题/正文/类型)。正文刻意混入:
# 具体事实型避雷、情绪发泄型尬黑、通篇溢美疑似暗广、正常攻略。
NOTES = {
    "故宫博物院": [
        {"title": "故宫一日游最全攻略,不走回头路", "type": "guide",
         "content": "早上8:30开门直接冲午门,先走中轴线:太和殿-中和殿-保和殿-乾清宫-坤宁宫-御花园,约2.5小时。然后东六宫,珍宝馆门票10元很值,钟表馆也推荐。中午冰窖餐厅简餐人均50。下午西六宫加角楼拍照,4点前到神武门出口。大门票60元,周一闭馆,提前7天在官方小程序抢票,节假日票秒没。珍宝馆钟表馆要单独约。建议租讲解器20元。防晒很重要,中轴线几乎没有树荫。",
         "author": "s1a2b3"},
        {"title": "故宫避雷!这几个坑千万别踩", "type": "avoid",
         "content": "1. 别买门口黄牛的快速通道票,官方小程序免费预约,黄牛票100-300纯智商税。2. 周一闭馆,很多攻略不写,白跑的人很多。3. 午门进神武门出不能走回头路,出口一定提前看。4. 珍宝馆单独收费不含在大门票里,只逛中轴线的话别期待看到。5. 节假日8:30-9:00安检排队40分钟以上,开门前1小时去排队比较稳。",
         "author": "s4c5d6"},
        {"title": "故宫真的绝了!!!此生必去!!", "type": "guide",
         "content": "太震撼了!!!红墙黄瓦美到窒息!!!每一处都超级出片!!!随手一拍就是大片!!!不去真的亏大了!!!姐妹们冲!!!",
         "author": "s7e8f9"},
        {"title": "故宫半日游体验(佛系版)", "type": "mixed",
         "content": "下午2点才到,人已经很多了,中轴线走完用了3个小时,时间主要花在排队上。殿内很多不开放只能隔着栏杆看,体验一般般。不过西边人少,拍照还行。门票60,没抢到珍宝馆的票有点遗憾。建议还是早上去,下午真的挤。",
         "author": "s0g1h2"},
    ],
    "颐和园": [
        {"title": "颐和园避雷+路线,省脚力版", "type": "avoid",
         "content": "1. 东宫门进、北宫门出是主流路线,但节假日人巨多,排队买票20分钟。2. 游船分大船小船,大船每人40,排队40分钟,走路绕湖其实只要30分钟,体力好别坐。3. 佛香阁单独收费10元,登顶视野好但要爬很高,老人小孩慎选。4. 园内餐饮贵,一瓶水8元,建议自带。5. 下午5点开始清场,4点半后很多殿门就关了,别太晚去。",
         "author": "s3i4j5"},
        {"title": "颐和园半日游,精华路线推荐", "type": "guide",
         "content": "东宫门进,先看仁寿殿,然后沿昆明湖东岸走到十七孔桥,过桥到南湖岛,再坐大船回石舫(船票40)。最后爬万寿山看佛香阁(另收10元),从北宫门出。全程4小时,门票30。春秋最舒服,冬天湖面结冰可以滑冰。建议带点吃的,园内贵。",
         "author": "s6k7l8"},
        {"title": "颐和园,再也不去了", "type": "avoid",
         "content": "太差了,又挤又乱,没什么好看的,浪费我半天时间,垃圾,不推荐任何人去。",
         "author": "s9m0n1"},
    ],
    "西湖": [
        {"title": "西湖避雷帖:本地人劝你别做这几件事", "type": "avoid",
         "content": "1. 断桥残雪就是一座普通石桥,旺季人挤人,拍照全靠挤,别抱太高期待。2. 湖心亭游船旺季排队1小时以上,船票55,不想排队的坐环湖观光车(10元一站)。3. 景区周边出租车难打,地铁1号线龙翔桥站最方便。4. 不要租景区门口那种单人自行车,很多路段禁行,会被收调度费。5. 节假日白堤会限流,建议工作日去。",
         "author": "s1a2b3"},
        {"title": "西湖一日游路线(免费版)", "type": "guide",
         "content": "上午:断桥-白堤-孤山-苏堤,全程步行约2.5小时,免费。中午在岳庙附近吃片儿川。下午:坐公交到雷峰塔(门票40,可上塔看全景),然后沿南山路走到长桥公园看日落。全程零门票也能玩得很舒服,西湖本身上不收费。春天苏堤桃花、秋天北山街梧桐都很美。",
         "author": "s4c5d6"},
        {"title": "西湖就是YYDS!!!必去必去!!!", "type": "guide",
         "content": "西湖真的太美了!!!仙境一样!!!随手一拍就是壁纸!!!不来绝对后悔!!!绝美!!!大家快冲!!!",
         "author": "s7e8f9"},
    ],
    "外滩": [
        {"title": "外滩避雷:夜景机位+人流提醒", "type": "avoid",
         "content": "1. 节假日晚上7-9点外滩观景平台限流,要排队分批上,人挤人,体验很差。2. 观景台免费,但沿线厕所排队长,建议提前解决。3. 江边风大,冬天晚上体感很冷,注意保暖。4. 别在平台上买荧光棒气球,又贵又挡视线。想看人少点的夜景,可以走到北外滩段,人少很多。",
         "author": "s0g1h2"},
        {"title": "外滩夜景攻略:最佳机位和时间", "type": "guide",
         "content": "看外滩夜景最好的时间是晚上6:30-7:30,天没全黑、灯刚亮,蓝调时刻拍照最美。最佳机位:外白渡桥上看陆家嘴三件套,或从北外滩拍外滩万国建筑群。观景台免费,地铁2号线南京东路站步行8分钟。想避开人流,工作日晚上去。",
         "author": "s3i4j5"},
    ],
    "宽窄巷子": [
        {"title": "宽窄巷子避雷:吃和逛的真实建议", "type": "avoid",
         "content": "1. 巷子里的小吃又贵又一般,一碗冰粉15-20,味道不如外面街边店,本地人基本不去巷子里吃。2. 采耳30-50一次,手法参差不齐,被坑的不少。3. 节假日人挤人,基本走不动,拍照全是人。4. 想体验地道成都,旁边的奎星楼街和泡桐树街人少性价比高。5. 巷子免费进,但店铺消费偏高。",
         "author": "s6k7l8"},
        {"title": "宽窄巷子打卡攻略", "type": "guide",
         "content": "宽巷子看老宅院、窄巷子逛文创店、井巷子看砖墙,三巷子串着走1-2小时。免费进,地铁4号线宽窄巷子站直达。晚上灯笼亮起来比白天好看。巷子里有川剧变脸表演,58一位含茶。",
         "author": "s9m0n1"},
    ],
    "大唐不夜城": [
        {"title": "大唐不夜城避雷:演出时间表很重要", "type": "avoid",
         "content": "1. 免费进,但各种互动演出有固定时间,不看时间表会错过,官方公众号有当日节目单。2. 盛唐密盒等热门演出要提前40分钟占位,晚了根本挤不进去。3. 街上卖的唐装出租拍照199起,质量一般,建议自己带或找正规店。4. 地铁3/4号线大雁塔站出站最方便,晚上10点后地铁人多要排队进站。5. 人多到走不动是常态,推婴儿车的基本走不了。",
         "author": "s1a2b3"},
        {"title": "大唐不夜城,绝美!!!", "type": "guide",
         "content": "大唐不夜城真的绝了!!!一秒穿越回大唐!!!灯光美到爆炸!!!不来真的白来西安!!!都给我冲!!!",
         "author": "s4c5d6"},
    ],
    "洪崖洞": [
        {"title": "洪崖洞避雷:千与千寻机位全攻略", "type": "avoid",
         "content": "1. 网红机位在千厮门大桥上,但桥上旺季挤满人,拍照要排队。2. 洪崖洞内部其实是个商业街,里面没什么可逛的,夜景主要看外观。3. 从解放碑步行过去约15分钟,别信路边拉客的'10元直达'。4. 晚上8-10点人最多,建议11点后去人少很多,灯光11点关。5. 免费进,但内部电梯排队20分钟起,建议走楼梯。",
         "author": "s7e8f9"},
        {"title": "洪崖洞夜景打卡攻略", "type": "guide",
         "content": "晚上8点后灯光全开最好看,最佳机位:千厮门大桥中段(免费)和江对岸重庆大剧院旁。洪崖洞本体免费进,内部是商业街,吃的不推荐。地铁6号线大剧院站过桥步行10分钟,或2号线临江门站步行15分钟。",
         "author": "s0g1h2"},
    ],
    "上海迪士尼乐园": [
        {"title": "迪士尼避雷:这些项目和时间点要避开", "type": "avoid",
         "content": "1. 飞跃地平线旺季排队90分钟起,开门第一个冲或者买尊享卡,不然纯浪费半天。2. 花车巡游前1小时城堡前就占满人了,晚了站后排什么都看不见。3. 园内餐饮贵,一个汉堡套餐100+,建议带点零食,但自热锅不让带。4. 烟花秀晚上9点开始,7点半就要去占位,不然只能看人头。5. 雨天部分项目停运,提前看天气预报,门票改期要提前一天。",
         "author": "s1a2b3"},
        {"title": "迪士尼一日游攻略(排队时间版)", "type": "guide",
         "content": "开园前20分钟到门口排队。进去先冲飞跃地平线,然后创极速光轮,这两个上午人最少。中午去明日世界附近吃饭,下午看花车巡游(3点半)和米奇童话专列。傍晚刷小项目,晚上看灯光烟花秀。单日门票475,两日联票划算一点。提前下载官方APP看实时排队时间,能省很多时间。",
         "author": "s4c5d6"},
    ],
    "成都大熊猫繁育研究基地": [
        {"title": "熊猫基地避雷:看猫时间很重要", "type": "avoid",
         "content": "1. 上午10点后熊猫基本都在睡觉,想看到活跃的猫必须7点半开园就冲。2. 观光车排队30分钟起,走路去月亮产房其实只要20分钟,别傻等。3. 节假日人挤人,栏杆前里三层外三层,小孩子根本看不到。4. 园区里买熊猫玩偶比外面贵一倍,门口小摊便宜。5. 夏天太热熊猫不出外场,全在室内玻璃房,体验差很多。",
         "author": "s7e8f9"},
        {"title": "熊猫基地半日攻略", "type": "guide",
         "content": "早上7:30开园冲月亮产房看幼崽,然后太阳产房,8-9点熊猫最活跃。中午前结束,全程3-4小时。门票55,地铁3号线熊猫大道站下车有接驳车。园区挺大,穿舒服的鞋。看熊猫吃竹子能看半小时,特别治愈。",
         "author": "s0g1h2"},
    ],
    "秦始皇兵马俑博物馆": [
        {"title": "兵马俑避雷:交通和讲解的坑", "type": "avoid",
         "content": "1. 一号坑人最多,节假日挤到栏杆前都站不稳,建议开门就冲一号坑。2. 门口拉客的'野导'50一位,讲得还没电子讲解器好,别花冤枉钱。3. 从西安市区过去要1.5小时,别信'30分钟直达',地铁9号线到华清池再换乘最稳。4. 景区出口那条商业街又长又绕,买东西要绕路半小时,别买。5. 周二到周日开放,周一闭馆,闭馆日白跑的人不少。",
         "author": "s3i4j5"},
        {"title": "兵马俑一日游攻略", "type": "guide",
         "content": "早上8:30开门进,先一号坑(最震撼),再三号坑二号坑,全程2-3小时。门票120,含秦始皇帝陵(坐免费摆渡车过去,丽山园人少值得逛)。官方讲解器30元或公众号免费语音。市区地铁9号线华清池站换乘游5路直达。建议带水,馆内一瓶8元。",
         "author": "s6k7l8"},
    ],
    "灵隐寺": [
        {"title": "灵隐寺体验(真实感受)", "type": "mixed",
         "content": "飞来峰门票45,进灵隐寺还要再买30香花券,两段收费有点肉疼。早上8点前人少,空气好,能听到诵经声。中午后人山人海,香火呛人。想上香建议自己带,寺里卖的一把30不便宜。整体古树参天很漂亮,但周末真的劝退,工作日去体验完全不同。",
         "author": "s9m0n1"},
    ],
    "玉龙雪山": [
        {"title": "玉龙雪山避雷:高反和索道的坑", "type": "avoid",
         "content": "1. 大索道票旺季抢不到,黄牛价翻3倍,提前3天在官方小程序抢。2. 海拔4506米,高反不是开玩笑,氧气瓶景区60一瓶,古城25,提前买。3. 别跟一日游团的'免费拍照',最后全是收费项目。4. 山上天气变化快,下雨索道会停运,行程别安排太满。5. 蓝月谷很美但别坐电瓶车,走栈道20分钟就到。",
         "author": "s1a2b3"},
        {"title": "玉龙雪山一日游攻略", "type": "guide",
         "content": "早上6点出发,大索道(冰川公园)8点前上,山顶看冰川,然后下来逛蓝月谷,下午去云杉坪。门票100+索道120(大索道)或60(云杉坪)。记得提前买氧气瓶和租羽绒服(山脚50)。山顶风大,拍照注意安全。全程不赶的话8小时。",
         "author": "s4c5d6"},
    ],
    "蜈支洲岛": [
        {"title": "蜈支洲岛避雷:上岛排队是重灾区", "type": "avoid",
         "content": "1. 节假日上岛排队2小时起,船票+门票168,建议早上8点前到码头。2. 岛上物价离谱,一瓶水10块,一碗面40,自己带吃的。3. 潜水项目680起,水质一般,不如去分界洲岛性价比高。4. 岛上电瓶车环岛120,其实徒步也能走,就是热。5. 下午4点半最后一班船离岛,别玩忘了时间。",
         "author": "s7e8f9"},
    ],
    "橘子洲": [
        {"title": "橘子洲打卡攻略(免费)", "type": "guide",
         "content": "地铁2号线橘子洲站直达,景区免费,观光小火车20元往返(走路4公里,建议坐车)。毛泽东雕像在洲头,拍照最佳机位在雕像正面台阶下。傍晚看湘江日落很美,周末人多,工作日人少。全程2小时。",
         "author": "s0g1h2"},
    ],
    "湖南省博物馆": [
        {"title": "省博避雷:辛追夫人参观要点", "type": "avoid",
         "content": "1. 免费但要提前7天预约,凌晨放票秒没,抢不到票的可以买临时展票进。2. 周一闭馆,别白跑。3. 辛追夫人棺椁在二楼,看的时候别开闪光灯,保安会喊。4. 馆内讲解器30,但公众号有免费语音导览,别花冤枉钱。5. 周末上午人最多,下午2点后人少些。",
         "author": "s3i4j5"},
    ],
    "长江索道": [
        {"title": "长江索道体验", "type": "mixed",
         "content": "单程20往返30,一次能坐60人,排队旺季要40分钟。车厢里人贴人,拍照视角一般,不如去白象居楼顶看索道穿过。本地人当交通工具,游客当景点,体验几分钟就结束。想拍空车厢要早上8点前坐。",
         "author": "s6k7l8"},
    ],
}


# 景区近似坐标(用于行程距离参考;正式数据以高德 POI 为准)
SPOT_COORDS = {
    "北京": {
        "故宫博物院": (116.397, 39.918), "颐和园": (116.275, 39.999),
        "八达岭长城": (116.018, 40.354), "天坛公园": (116.412, 39.882),
        "北京环球影城": (116.668, 39.867),
    },
    "上海": {
        "外滩": (121.490, 31.240), "上海迪士尼乐园": (121.657, 31.144),
        "豫园": (121.493, 31.227), "武康路": (121.442, 31.210),
    },
    "广州": {
        "广州塔": (113.324, 23.106), "长隆野生动物世界": (113.314, 22.999),
        "沙面": (113.240, 23.107), "陈家祠": (113.245, 23.131),
    },
    "成都": {
        "宽窄巷子": (104.056, 30.670), "成都大熊猫繁育研究基地": (104.147, 30.736),
        "都江堰": (103.619, 30.998), "锦里古街": (104.050, 30.646),
    },
    "重庆": {
        "洪崖洞": (106.578, 29.562), "磁器口古镇": (106.454, 29.575),
        "长江索道": (106.583, 29.560), "武隆天生三桥": (107.755, 29.395),
    },
    "西安": {
        "秦始皇兵马俑博物馆": (109.279, 34.384), "大雁塔": (108.964, 34.219),
        "大唐不夜城": (108.961, 34.217), "西安城墙": (108.943, 34.258),
    },
    "杭州": {
        "西湖": (120.150, 30.245), "灵隐寺": (120.098, 30.241),
        "千岛湖": (119.036, 29.604), "西溪国家湿地公园": (120.063, 30.269),
    },
    "三亚": {
        "亚龙湾": (109.637, 18.230), "蜈支洲岛": (109.762, 18.309),
        "天涯海角": (109.358, 18.294), "南山文化旅游区": (109.208, 18.312),
    },
    "丽江": {
        "丽江古城": (100.234, 26.872), "玉龙雪山": (100.180, 27.107),
        "泸沽湖": (100.771, 27.697), "束河古镇": (100.205, 26.898),
        "四方街": (100.234, 26.872), "黑龙潭公园": (100.250, 26.880),
    },
    "昆明": {
        "石林风景名胜区": (103.33, 24.81), "云南省博物馆": (102.73, 24.98),
        "滇池海埂公园": (102.66, 24.96), "西山龙门": (102.63, 24.96),
        "翠湖公园": (102.70, 25.04), "斗南花市": (102.763, 24.944),
        "云南民族村": (102.702, 24.963), "海埂大坝": (102.639, 24.969),
        "南屏街": (102.71, 25.04),
    },
    "大理": {
        "崇圣寺三塔文化旅游区": (100.15, 25.71), "大理古城": (100.16, 25.69),
        "洱海": (100.21, 25.78), "双廊古镇": (100.19, 25.92),
        "人民路": (100.16, 25.70),
    },
    # 全国知名 5A/4A 景点真实坐标(修正"回退复制成市中心"的假坐标,保证远项目判定)
    "天津": {"天津古文化街旅游区": (117.19, 39.14)},
    "承德": {"承德避暑山庄及周围寺庙": (117.94, 40.99)},
    "秦皇岛": {"山海关景区": (119.76, 40.01)},
    "石家庄": {"西柏坡景区": (114.04, 38.32)},
    "唐山": {"清东陵景区": (117.65, 40.19)},
    "忻州": {"五台山风景名胜区": (113.59, 39.01)},
    "晋中": {"平遥古城": (112.18, 37.20)},
    "大同": {"云冈石窟": (113.13, 40.11)},
    "临汾": {"黄河壶口瀑布旅游区": (110.44, 36.15)},
    "鄂尔多斯": {"成吉思汗陵旅游区": (109.85, 39.40)},
    "沈阳": {"沈阳故宫博物院": (123.45, 41.80)},
    "大连": {"老虎滩海洋公园": (121.68, 38.87)},
    "本溪": {"本溪水洞风景名胜区": (124.10, 41.31)},
    "鞍山": {"千山风景名胜区": (123.03, 41.03)},
    "延边": {"长白山景区": (128.08, 42.01)},
    "长春": {"伪满皇宫博物院": (125.34, 43.90)},
    "哈尔滨": {"太阳岛风景区": (126.61, 45.79)},
    "牡丹江": {"镜泊湖风景名胜区": (128.72, 43.85)},
    "黑河": {"五大连池风景区": (126.20, 48.72)},
    "苏州": {"拙政园": (120.63, 31.32)},
    "扬州": {"瘦西湖风景区": (119.42, 32.42)},
    "无锡": {"灵山胜境景区": (120.19, 31.47)},
    "常州": {"中华恐龙园": (119.98, 31.80)},
    "镇江": {"金山景区": (119.42, 32.24)},
    "嘉兴": {"乌镇景区": (120.49, 30.74)},
    "舟山": {"普陀山风景名胜区": (122.39, 29.98)},
    "温州": {"雁荡山风景名胜区": (121.07, 28.37)},
    "金华": {"横店影视城": (120.30, 29.09)},
    "黄山市": {"屯溪老街": (118.31, 29.71)},
    "池州": {"九华山风景区": (117.81, 30.48)},
    "安庆": {"天柱山风景区": (116.48, 30.72)},
    "南平": {"武夷山风景名胜区": (118.03, 27.65)},
    "厦门": {"鼓浪屿风景名胜区": (118.07, 24.45)},
    "龙岩": {"福建土楼(永定)景区": (116.97, 24.67)},
    "九江": {"庐山风景名胜区": (115.99, 29.55)},
    "鹰潭": {"龙虎山风景名胜区": (116.99, 28.04)},
    "南昌": {"滕王阁旅游区": (115.88, 28.68)},
    "泰安": {"泰山风景名胜区": (117.10, 36.26)},
    "青岛": {"崂山风景区": (120.62, 36.19)},
    "济宁": {"曲阜明故城(三孔)": (116.99, 35.60), "曲阜明故城": (116.99, 35.60)},
    "烟台": {"蓬莱阁旅游区": (120.76, 37.83)},
    "济南": {"趵突泉景区": (117.01, 36.66)},
    "威海": {"刘公岛景区": (122.19, 37.50)},
    "枣庄": {"台儿庄古城": (117.73, 34.56)},
    "登封": {"嵩山少林景区": (112.93, 34.51)},
    "洛阳": {"龙门石窟": (112.47, 34.56)},
    "焦作": {"云台山风景名胜区": (113.43, 35.42)},
    "开封": {"清明上河园": (114.34, 34.80)},
    "栾川": {"老君山景区": (111.67, 33.72)},
    "武汉": {"黄鹤楼公园": (114.31, 30.55)},
    "十堰": {"武当山风景区": (111.00, 32.40)},
    "宜昌": {"三峡大坝旅游区": (111.01, 30.83)},
    "神农架": {"神农架生态旅游区": (110.30, 31.70)},
    "恩施": {"恩施大峡谷景区": (109.12, 30.55)},
    "张家界": {"张家界武陵源旅游区": (110.54, 29.35)},
    "衡阳": {"衡山风景名胜区": (112.70, 27.25)},
    "湘西": {"凤凰古城": (109.60, 27.95)},
    "湘潭": {"韶山旅游区": (112.53, 27.92)},
    "韶关": {"丹霞山风景名胜区": (113.73, 24.97)},
    "惠州": {"罗浮山风景名胜区": (114.07, 23.27)},
    "江门": {"开平碉楼文化旅游区": (112.61, 22.31)},
    "佛山": {"西樵山风景名胜区": (112.98, 22.93)},
    "崇左": {"德天跨国瀑布景区": (106.72, 22.85)},
    "北海": {"北海银滩旅游度假区": (109.13, 21.40)},
    "保亭": {"呀诺达雨林文化旅游区": (109.63, 18.53)},
    "阿坝": {"九寨沟风景名胜区": (103.92, 33.26)},
    "甘孜": {"稻城亚丁景区": (100.30, 28.45)},
    "安顺": {"黄果树风景名胜区": (105.67, 25.98)},
    "铜仁": {"梵净山旅游景区": (108.69, 27.93)},
    "黔南": {"荔波樟江风景名胜区": (107.88, 25.24)},
    "香格里拉": {"普达措国家公园": (99.92, 27.90)},
    "西双版纳": {"中国科学院西双版纳热带植物园": (101.25, 21.92)},
    "渭南": {"华山风景名胜区": (110.09, 34.48)},
    "宝鸡": {"法门寺佛文化景区": (107.90, 34.44)},
    "天水": {"麦积山石窟": (106.00, 34.35)},
    "张掖": {"张掖七彩丹霞景区": (100.12, 38.93)},
    "海北": {"青海湖景区": (100.10, 36.88)},
    "西宁": {"塔尔寺景区": (101.57, 36.48)},
    "中卫": {"沙坡头旅游景区": (105.17, 37.47)},
    "银川": {"沙湖旅游景区": (106.35, 38.80)},
    "昌吉": {"天山天池风景名胜区": (88.13, 43.88)},
    "阿勒泰": {"喀纳斯景区": (87.04, 48.72)},
    "伊犁": {"那拉提旅游风景区": (83.85, 43.34)},
    "吐鲁番": {"葡萄沟风景区": (89.20, 42.93)},
    "黔东南": {"西江千户苗寨": (108.17, 26.49)},
    "红河": {"建水古城": (102.83, 23.62)},
    "日喀则": {"扎什伦布寺": (88.88, 29.27)},
    "广汉": {"三星堆博物馆": (104.19, 30.99)},
    "平凉": {"崆峒古镇": (106.51, 35.56)},
    "陇南": {"官鹅沟景区": (104.92, 33.95)},
    "重庆": {"大足石刻景区": (105.70, 29.70), "巫山小三峡-小小三峡": (109.88, 31.07),
             "酉阳桃花源景区": (108.77, 28.84)},
    "桂林": {"漓江风景名胜区": (110.50, 24.93), "象鼻山": (110.30, 25.27)},
    "延安": {"宝塔山": (109.49, 36.59), "黄帝陵": (109.26, 35.58)},
    "井冈山": {"井冈山风景旅游区": (114.13, 26.58)},
    "深圳": {"世界之窗": (113.97, 22.54)},
    "乌鲁木齐": {"新疆国际大巴扎": (87.62, 43.78)},
    "长沙": {
        "岳麓山": (112.935, 28.190), "橘子洲": (112.958, 28.197),
        "湖南省博物馆": (112.995, 28.216), "太平街": (112.977, 28.198),
    },
}


def update_coords(conn: sqlite3.Connection) -> int:
    """为种子景区回填真实坐标:
    - 缺失坐标(lng IS NULL)的景点;
    - 坐标被"回退复制成市中心"(与城市坐标完全一致)的景点 —— 这类假坐标会让
      "距市中心≥25km=远项目"的判定失效(如石林/五台山/泰山等)。
    返回更新条数。"""
    n = 0
    for city, coords in SPOT_COORDS.items():
        city_row = conn.execute("SELECT id FROM cities WHERE name=?", (city,)).fetchone()
        if city_row is None:
            continue
        cid = city_row["id"]
        for spot, (lng, lat) in coords.items():
            # 幂等:坐标不是目标值就更新(覆盖缺失/回退复制的假坐标)
            cur = conn.execute(
                "UPDATE spots SET lng=?, lat=? WHERE city_id=? AND name=? AND "
                "(lng IS NULL OR abs(lng-?)>1e-6 OR abs(lat-?)>1e-6)",
                (lng, lat, cid, spot, lng, lat))
            n += cur.rowcount
    conn.commit()
    return n


def supplement_sample_notes(conn: sqlite3.Connection) -> int:
    """老库增量补种:预设示例笔记但该景区尚无笔记时插入(幂等)。返回插入条数。"""
    n = 0
    for spot_name, notes in NOTES.items():
        row = conn.execute("SELECT id FROM spots WHERE name=?", (spot_name,)).fetchone()
        if row is None:
            continue
        sid = row["id"]
        has = conn.execute("SELECT 1 FROM notes WHERE spot_id=? LIMIT 1", (sid,)).fetchone()
        if has:
            continue
        for note in notes:
            conn.execute(
                "INSERT INTO notes(spot_id, title, content, author_hash, note_type, is_sample) "
                "VALUES(?,?,?,?,?,1)",
                (sid, note["title"], note["content"], note["author"], note["type"]),
            )
            n += 1
    conn.commit()
    return n


def seed_5a(conn: sqlite3.Connection) -> tuple:
    """全国 5A 景区扩充(幂等):新增城市与景区,标记 grade='5A'。"""
    from .seed_5a import CITY_COORDS, SPOT_COORDS_5A, SPOTS_5A

    added_cities = 0
    added_spots = 0
    for city, (lng, lat) in CITY_COORDS.items():
        cur = conn.execute(
            "INSERT OR IGNORE INTO cities(name, province, lng, lat) VALUES(?,?,?,?)",
            (city, "", lng, lat),
        )
        added_cities += cur.rowcount
    for province, city, spot in SPOTS_5A:
        row = conn.execute("SELECT id FROM cities WHERE name=?", (city,)).fetchone()
        if row is None:
            continue
        cid = row["id"]
        conn.execute(
            "UPDATE cities SET province=? WHERE id=? AND (province IS NULL OR province='')",
            (_norm_province(province), cid),
        )
        lng, lat = SPOT_COORDS_5A.get(spot, CITY_COORDS.get(city, (None, None)))
        cur = conn.execute(
            "INSERT OR IGNORE INTO spots(city_id, name, grade, lng, lat) VALUES(?,?,?,?,?)",
            (cid, spot, "5A", lng, lat),
        )
        added_spots += cur.rowcount
    conn.commit()
    if added_cities or added_spots:
        print(f"seed_5a: +{added_cities} 城市, +{added_spots} 个 5A 景区")
    return added_cities, added_spots


def seed_loops(conn: sqlite3.Connection) -> tuple:
    """精选自驾环线(甘南/川西/青甘/滇西北/北疆)入库(幂等),grade 留空=非评级。"""
    from .seed_5a import CITY_COORDS as CITY_COORDS_5A
    from .seed_loops import CITY_COORDS_LOOPS, LOOPS

    coords = {**CITY_COORDS_5A, **CITY_COORDS_LOOPS}  # 5A 城市坐标兜底(如 敦煌/香格里拉)
    added_cities = 0
    added_spots = 0
    for city, (lng, lat) in coords.items():
        cur = conn.execute(
            "INSERT OR IGNORE INTO cities(name, province, lng, lat) VALUES(?,?,?,?)",
            (city, "", lng, lat),
        )
        added_cities += cur.rowcount
    for loop_name, loop in LOOPS.items():
        for province, city, spot, tags, slng, slat in loop["spots"]:
            row = conn.execute("SELECT id FROM cities WHERE name=?", (city,)).fetchone()
            if row is None:
                continue
            cid = row["id"]
            conn.execute(
                "UPDATE cities SET province=? WHERE id=? AND (province IS NULL OR province='')",
                (_norm_province(province), cid),
            )
            lng, lat = coords[city]
            all_tags = [f"环线:{loop_name}"] + tags
            cur = conn.execute(
                "INSERT INTO spots(city_id, name, tags, lng, lat) VALUES(?,?,?,?,?) "
                "ON CONFLICT(city_id, name) DO UPDATE SET "
                "tags=excluded.tags, lng=excluded.lng, lat=excluded.lat",
                (cid, spot, json.dumps(all_tags, ensure_ascii=False),
                 slng if slng is not None else lng, slat if slat is not None else lat),
            )
            added_spots += cur.rowcount
    conn.commit()
    if added_cities or added_spots:
        print(f"seed_loops: +{added_cities} 城市, +{added_spots} 个环线点位")
    return added_cities, added_spots


def seed_4a(conn: sqlite3.Connection) -> tuple:
    """4A 级景区(首批,逐步完善):扩充城市覆盖面,grade='4A'。"""
    from .seed_4a import CITY_COORDS_4A, SPOTS_4A
    from .seed_5a import CITY_COORDS as CITY_COORDS_5A
    from .seed_loops import CITY_COORDS_LOOPS

    coords = {**CITY_COORDS_5A, **CITY_COORDS_LOOPS, **CITY_COORDS_4A}
    added_cities = 0
    added_spots = 0
    skipped = []
    for city, (lng, lat) in CITY_COORDS_4A.items():
        cur = conn.execute(
            "INSERT OR IGNORE INTO cities(name, province, lng, lat) VALUES(?,?,?,?)",
            (city, "", lng, lat),
        )
        added_cities += cur.rowcount
    for province, city, spot, tags, slng, slat in SPOTS_4A:
        if city not in coords:
            skipped.append(f"{city}/{spot}")
            continue
        row = conn.execute("SELECT id FROM cities WHERE name=?", (city,)).fetchone()
        if row is None:
            continue
        cid = row["id"]
        conn.execute(
            "UPDATE cities SET province=? WHERE id=? AND (province IS NULL OR province='')",
            (_norm_province(province), cid),
        )
        lng, lat = coords[city]
        cur = conn.execute(
            "INSERT INTO spots(city_id, name, grade, tags, lng, lat) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(city_id, name) DO UPDATE SET "
            "grade=excluded.grade, tags=excluded.tags, lng=excluded.lng, lat=excluded.lat",
            (cid, spot, "4A", json.dumps(tags, ensure_ascii=False),
             slng if slng is not None else lng, slat if slat is not None else lat),
        )
        added_spots += cur.rowcount
    conn.commit()
    if added_cities or added_spots:
        print(f"seed_4a: +{added_cities} 城市, +{added_spots} 个 4A 景区"
              + (f";跳过无坐标: {skipped[:3]}" if skipped else ""))
    return added_cities, added_spots


def seed_prices(conn: sqlite3.Connection) -> int:
    """门票参考价入库(幂等):按景点名匹配,更新 price 列。返回匹配条数。"""
    from .seed_prices import PRICES

    n = 0
    unmatched = []
    for name, price in PRICES.items():
        cur = conn.execute("UPDATE spots SET price=? WHERE name=? AND price IS NULL", (price, name))
        if cur.rowcount:
            n += 1
        elif conn.execute("SELECT 1 FROM spots WHERE name=? LIMIT 1", (name,)).fetchone() is None:
            unmatched.append(name)
    conn.commit()
    if unmatched:
        print(f"seed_prices: 未匹配 {len(unmatched)} 个: {unmatched[:5]}...")
    return n


def seed_stays(conn: sqlite3.Connection) -> int:
    """住宿推荐知识库入库(幂等,区域级,无具体商家名)。"""
    from .seed_stays import STAYS

    n = 0
    for town, city, lng, lat, lo, hi, note, serve in STAYS:
        cur = conn.execute(
            "INSERT OR REPLACE INTO stays(town, city, lng, lat, price_low, price_high, note, serve) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (town, city, lng, lat, lo, hi, note, serve),
        )
        n += cur.rowcount
    conn.commit()
    return n


def seed_museums(conn: sqlite3.Connection) -> tuple:
    """著名博物馆入库(城市模式项目之一,幂等)。"""
    from .seed_5a import CITY_COORDS as C5A
    from .seed_loops import CITY_COORDS_LOOPS
    from .seed_4a import CITY_COORDS_4A
    from .seed_museums import MUSEUMS

    coords = {**C5A, **CITY_COORDS_LOOPS, **CITY_COORDS_4A}
    added_cities = 0
    added_spots = 0
    for province, city, name, addr, lng, lat in MUSEUMS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO cities(name, province, lng, lat) VALUES(?,?,?,?)",
            (city, "", coords.get(city, (None, None))[0], coords.get(city, (None, None))[1]),
        )
        added_cities += cur.rowcount
        row = conn.execute("SELECT id FROM cities WHERE name=?", (city,)).fetchone()
        if row is None:
            continue
        cid = row["id"]
        conn.execute(
            "UPDATE cities SET province=? WHERE id=? AND (province IS NULL OR province='')",
            (_norm_province(province), cid),
        )
        cur = conn.execute(
            "INSERT OR IGNORE INTO spots(city_id, name, address, tags, lng, lat) VALUES(?,?,?,?,?,?)",
            (cid, name, addr, json.dumps(["博物馆"], ensure_ascii=False), lng, lat),
        )
        added_spots += cur.rowcount
    conn.commit()
    if added_cities or added_spots:
        print(f"seed_museums: +{added_cities} 城市, +{added_spots} 个博物馆")
    return added_cities, added_spots


def seed_foods(conn: sqlite3.Connection) -> int:
    """城市美食知识库入库(幂等:先删后插,区域级防暗广)。
    美食街坐标:STREET_COORDS 优先,否则回退城市中心(便于"城市美食地图"标注)。"""
    from .seed_foods import FOODS, STREET_COORDS

    n = 0
    for city, kind, name, where, lo, hi, note in FOODS:
        conn.execute(
            "DELETE FROM city_foods WHERE city=? AND kind=? AND name=?",
            (city, kind, name),
        )
        lng = lat = None
        if kind == "street":
            if name in STREET_COORDS:
                lng, lat = STREET_COORDS[name]
            else:
                crow = conn.execute("SELECT lng, lat FROM cities WHERE name=?", (city,)).fetchone()
                if crow:
                    lng, lat = crow["lng"], crow["lat"]
        conn.execute(
            "INSERT INTO city_foods(city, kind, name, where_hint, price_low, price_high, note, lng, lat) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (city, kind, name, where, lo, hi, note, lng, lat),
        )
        n += 1
    conn.commit()
    return n


def seed_food_spots(conn: sqlite3.Connection) -> tuple:
    """美食街/聚集区升级为正式"景点"(可上图/加购物车/看口碑卡)。

    从 city_foods(kind='street') 同步为 spots,标签含"美食街";
    并为热门美食街补示例口碑笔记(演示评价界面)。
    """
    from .seed_foods import STREET_SAMPLE_NOTES

    n_spots = 0
    n_notes = 0
    rows = conn.execute(
        "SELECT city, name, lng, lat FROM city_foods WHERE kind='street' AND lng IS NOT NULL"
    ).fetchall()
    for r in rows:
        city_row = conn.execute("SELECT id FROM cities WHERE name=?", (r["city"],)).fetchone()
        if city_row is None:
            continue
        cid = city_row["id"]
        cur = conn.execute(
            "INSERT INTO spots(city_id, name, tags, lng, lat) VALUES(?,?,?,?,?) "
            "ON CONFLICT(city_id, name) DO UPDATE SET "
            "tags=excluded.tags, lng=excluded.lng, lat=excluded.lat",
            (cid, r["name"], json.dumps(["美食街", "美食"], ensure_ascii=False),
             r["lng"], r["lat"]),
        )
        if cur.rowcount:
            n_spots += 1
        # 示例口碑笔记(该美食街尚无笔记时)
        notes = STREET_SAMPLE_NOTES.get(r["name"], [])
        if notes:
            has = conn.execute(
                "SELECT 1 FROM notes n JOIN spots s ON s.id=n.spot_id "
                "WHERE s.city_id=? AND s.name=? LIMIT 1", (cid, r["name"])
            ).fetchone()
            if has is None:
                row2 = conn.execute(
                    "SELECT id FROM spots WHERE city_id=? AND name=?", (cid, r["name"])
                ).fetchone()
                for note in notes:
                    conn.execute(
                        "INSERT INTO notes(spot_id, title, content, author_hash, note_type, is_sample) "
                        "VALUES(?,?,?,?,?,1)",
                        (row2["id"], note["title"], note["content"],
                         note.get("author", "sample"), note["type"]),
                    )
                    n_notes += 1
                # 新笔记即计算口碑卡(演示"美食街=景点"的评价界面;已存在则不重算)
                has_summary = conn.execute(
                    "SELECT 1 FROM spot_summaries WHERE spot_id=?", (row2["id"],)
                ).fetchone()
                if has_summary is None:
                    try:
                        from datetime import datetime
                        from ..ai.pipeline import summarize_spot

                        ns = conn.execute(
                            "SELECT * FROM notes WHERE spot_id=? ORDER BY id", (row2["id"],)
                        ).fetchall()
                        card = summarize_spot(r["name"], [dict(x) for x in ns])
                        conn.execute(
                            "INSERT OR REPLACE INTO spot_summaries(spot_id, summary_json, updated_at) "
                            "VALUES(?,?,?)",
                            (row2["id"], json.dumps(card, ensure_ascii=False),
                             datetime.now().isoformat(timespec="seconds")),
                        )
                    except Exception as e:
                        print(f"  [seed_food_spots] {r['name']} 口碑卡生成失败: {e}")
    conn.commit()
    if n_spots or n_notes:
        print(f"seed_food_spots: +{n_spots} 美食街景点, +{n_notes} 条示例口碑")
    return n_spots, n_notes


def seed_landmarks(conn: sqlite3.Connection) -> tuple:
    """城市地标:知名公园 + 商圈/商业街(与景点同机制)。

    与美食街同名者合并标签(如中央大街=美食街+商圈);新景点附少量示例口碑笔记。
    """
    from .seed_landmarks import COMMERCIAL, LANDMARK_SAMPLE_NOTES, PARKS

    n_spots = 0
    n_notes = 0

    def _upsert(province, city, name, lng, lat, new_tags, commercial, sample_notes):
        nonlocal n_spots, n_notes
        crow = conn.execute("SELECT id FROM cities WHERE name=?", (city,)).fetchone()
        if crow is None:
            return
        cid = crow["id"]
        conn.execute(
            "UPDATE cities SET province=? WHERE id=? AND (province IS NULL OR province='')",
            (_norm_province(province), cid),
        )
        row = conn.execute(
            "SELECT id, tags FROM spots WHERE city_id=? AND name=?", (cid, name)
        ).fetchone()
        com_json = json.dumps(commercial, ensure_ascii=False) if commercial else None
        if row is None:
            cur = conn.execute(
                "INSERT INTO spots(city_id, name, tags, lng, lat, commercial) VALUES(?,?,?,?,?,?)",
                (cid, name, json.dumps(new_tags, ensure_ascii=False), lng, lat, com_json),
            )
            n_spots += 1
            spot_id = cur.lastrowid
        else:
            old = json.loads(row["tags"] or "[]")
            merged = list(dict.fromkeys(old + new_tags))
            conn.execute(
                "UPDATE spots SET tags=?, lng=?, lat=?, commercial=COALESCE(?, commercial) WHERE id=?",
                (json.dumps(merged, ensure_ascii=False), lng, lat, com_json, row["id"]),
            )
            spot_id = row["id"]
        # 示例口碑(尚无笔记时)
        if sample_notes:
            has = conn.execute("SELECT 1 FROM notes WHERE spot_id=? LIMIT 1", (spot_id,)).fetchone()
            if has is None:
                from datetime import datetime

                for note in sample_notes:
                    conn.execute(
                        "INSERT INTO notes(spot_id, title, content, author_hash, note_type, is_sample) "
                        "VALUES(?,?,?,?,?,1)",
                        (spot_id, note["title"], note["content"],
                         note.get("author", "sample"), note["type"]),
                    )
                    n_notes += 1
                try:
                    from ..ai.pipeline import summarize_spot

                    ns = conn.execute(
                        "SELECT * FROM notes WHERE spot_id=? ORDER BY id", (spot_id,)
                    ).fetchall()
                    card = summarize_spot(name, [dict(x) for x in ns])
                    conn.execute(
                        "INSERT OR REPLACE INTO spot_summaries(spot_id, summary_json, updated_at) VALUES(?,?,?)",
                        (spot_id, json.dumps(card, ensure_ascii=False),
                         datetime.now().isoformat(timespec="seconds")),
                    )
                except Exception as e:
                    print(f"  [seed_landmarks] {name} 口碑卡失败: {e}")

    for province, city, name, lng, lat in PARKS:
        _upsert(province, city, name, lng, lat, ["公园"], None,
                LANDMARK_SAMPLE_NOTES.get(name))
    for province, city, name, lng, lat, ctype, tier in COMMERCIAL:
        _upsert(province, city, name, lng, lat, ["商圈", "商业街"],
                {"type": ctype, "tier": tier},
                LANDMARK_SAMPLE_NOTES.get(name))
    conn.commit()
    if n_spots or n_notes:
        print(f"seed_landmarks: +{n_spots} 城市地标, +{n_notes} 条示例口碑")
    return n_spots, n_notes


def seed_alternatives(conn: sqlite3.Connection) -> int:
    """高门票景点平替推荐(幂等):平替景点不存在则自动创建。"""
    from .seed_alternatives import ALTERNATIVES

    n = 0
    created = 0
    for main_name, cfg in ALTERNATIVES.items():
        cfgs = cfg if isinstance(cfg, list) else [cfg]  # 支持一主多平替
        main = conn.execute("SELECT id FROM spots WHERE name=?", (main_name,)).fetchone()
        if main is None:
            continue
        for c in cfgs:
            alt_name, city, tags, slng, slat = c["alt"]
            city_row = conn.execute("SELECT id FROM cities WHERE name=?", (city,)).fetchone()
            if city_row is None:
                continue
            cid = city_row["id"]
            alt = conn.execute(
                "SELECT id FROM spots WHERE city_id=? AND name=?", (cid, alt_name)
            ).fetchone()
            if alt is None:
                cur = conn.execute(
                    "INSERT INTO spots(city_id, name, tags, lng, lat) VALUES(?,?,?,?,?)",
                    (cid, alt_name, json.dumps(tags, ensure_ascii=False), slng, slat),
                )
                alt_id = cur.lastrowid
                created += 1
            else:
                alt_id = alt["id"]
            conn.execute(
                "INSERT OR REPLACE INTO spot_alternatives(spot_id, alt_spot_id, price_note, note, downsides_json) "
                "VALUES(?,?,?,?,?)",
                (main["id"], alt_id, c["price_note"], c["note"],
                 json.dumps(c["downsides"], ensure_ascii=False)),
            )
            n += 1
    conn.commit()
    if n:
        print(f"seed_alternatives: {n} 组平替推荐(自动创建平替景点 {created} 个)")
    return n


def seed_all(conn: sqlite3.Connection) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    city_ids = {}
    for c in CITIES:
        cur = conn.execute(
            "INSERT INTO cities(name, province, lng, lat) VALUES(?,?,?,?)",
            (c["name"], c["province"], c["lng"], c["lat"]),
        )
        city_ids[c["name"]] = cur.lastrowid

    spot_ids = {}
    for city, spots in SPOTS.items():
        for s in spots:
            cur = conn.execute(
                "INSERT INTO spots(city_id, name, poi_rating, address, tags) VALUES(?,?,?,?,?)",
                (city_ids[city], s["name"], s["rating"], s["address"], json.dumps(s["tags"], ensure_ascii=False)),
            )
            spot_ids[(city, s["name"])] = cur.lastrowid

    for spot_name, notes in NOTES.items():
        # 用第一个出现的城市-景点匹配
        sid = next((v for k, v in spot_ids.items() if k[1] == spot_name), None)
        if sid is None:
            continue
        for n in notes:
            conn.execute(
                "INSERT INTO notes(spot_id, title, content, author_hash, note_type, is_sample) "
                "VALUES(?,?,?,?,?,1)",
                (sid, n["title"], n["content"], n["author"], n["type"]),
            )
    conn.commit()
    print(f"seed done: {len(CITIES)} cities, {len(spot_ids)} spots, "
          f"{sum(len(v) for v in NOTES.values())} sample notes")


def seed_popular(conn: sqlite3.Connection) -> int:
    """精选大众可玩景点入库(幂等):花市/海洋馆/科技馆/主题乐园/名楼/特色街区等。
    城市不存在时自动创建(坐标取该景点坐标兜底);与 5A/4A/美食街互补。"""
    from .seed_5a import CITY_COORDS as C5A
    from .seed_popular import POPULAR_SPOTS

    added_cities = 0
    added_spots = 0
    for city, name, tags, lng, lat in POPULAR_SPOTS:
        row = conn.execute("SELECT id FROM cities WHERE name=?", (city,)).fetchone()
        if row is None:
            clng, clat = C5A.get(city, (lng, lat))
            cur = conn.execute(
                "INSERT OR IGNORE INTO cities(name, province, lng, lat) VALUES(?,?,?,?)",
                (city, "", clng, clat),
            )
            added_cities += cur.rowcount
            row = conn.execute("SELECT id FROM cities WHERE name=?", (city,)).fetchone()
        if row is None:
            continue
        cid = row["id"]
        cur = conn.execute(
            "INSERT OR IGNORE INTO spots(city_id, name, tags, lng, lat) VALUES(?,?,?,?,?)",
            (cid, name, json.dumps(tags, ensure_ascii=False), lng, lat),
        )
        added_spots += cur.rowcount
    conn.commit()
    if added_cities or added_spots:
        print(f"seed_popular: +{added_cities} 城市, +{added_spots} 个精选景点")
    return added_spots
