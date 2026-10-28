# 铁路工作台来源

由本机 `rail-atlas` 项目的前端构建产物整合而来。原项目保留不动。
本项目新增按需加载、同源消息交接、旅行交通清单与 Python 票价适配层。

时刻表：wensimehrp (Jeremy Gao)，China Railway GTFS，CC BY 4.0。
数据快照：https://github.com/wensimehrp/chinese-railway-gtfs/releases/tag/gtfs-20261020-044926
许可：https://creativecommons.org/licenses/by/4.0/
坐标：OpenStreetMap，WGS84；行政边界：DataV。
网络数据经过筛选、压缩与城市分组；原始来源校验信息见 `data/provenance.json`。
该来源文件保留了早期估价说明；当前产品只采用成功取得的公开报价，缺价不参与费用排序。

静态时刻表不是实际开行、余票、晚点或换乘保证。票价来自匿名公开查询，
不读取乘客账号，不购票，不绕过验证码或访问限制；失败时保持“待核价”。
保存到旅行中的费用是带时间的参考快照，出发前请向 12306 核实。
