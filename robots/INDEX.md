# 机器人板块研究 INDEX

> 更新日期:2026-06-10
> 本目录用途:作为美股交易者研究机器人板块的结构化入口

---

## 一、文件导航

### 📂 赛道全景
| 文件 | 内容 | 关键词 |
|---|---|---|
| [humanoid.md](humanoid.md) | 人形机器人赛道 | Tesla / Figure / 1X / Unitree |
| [medical_surgical.md](medical_surgical.md) | 手术 / 医疗机器人 | ISRG / SYK / MDT / PRCT |
| [warehouse_logistics.md](warehouse_logistics.md) | 仓储 / 物流机器人 | SYM / SERV / Locus |
| [industrial.md](industrial.md) | 工业机器人 | Fanuc / TER / ROK |

### 📂 零部件维度
| 文件 | 内容 | 关键词 |
|---|---|---|
| [actuator.md](actuator.md) | 执行器 / 伺服电机 | Yaskawa / Nidec / ALNT |
| [reducer.md](reducer.md) | 减速器 / 丝杠 | Harmonic Drive / Schaeffler |
| [dexterous_hand.md](dexterous_hand.md) | 灵巧手 | 自研 + GelSight |
| [sensor.md](sensor.md) | 传感器(视觉/力/触/IMU/雷达) | Sony / HSAI / OUST |

### 📂 专题 / 横切
| 文件 | 内容 |
|---|---|
| [optimus_supply_chain.md](optimus_supply_chain.md) | Tesla Optimus 全产业链 |
| [private_players.md](private_players.md) | Figure / 1X / Unitree 对比 |
| [china_vs_us.md](china_vs_us.md) | 中美产业格局 |

### 📂 公司深挖(companies/)
| 文件 | 公司 | 角色 |
|---|---|---|
| [companies/TSLA.md](companies/TSLA.md) | Tesla | 整机 + AI 双引擎 |
| [companies/ISRG.md](companies/ISRG.md) | Intuitive Surgical | 医疗机器人龙头 |
| [companies/SYM.md](companies/SYM.md) | Symbotic | 仓储自动化龙头 |
| [companies/TER.md](companies/TER.md) | Teradyne | 美股工业机器人 |
| [companies/ALNT.md](companies/ALNT.md) | Allient | 微型电机弹性 |
| [companies/HarmonicDrive.md](companies/HarmonicDrive.md) | Harmonic Drive | 谐波减速器全球垄断 |
| [companies/HSAI.md](companies/HSAI.md) | Hesai | 激光雷达机器人受益 |
| [companies/Figure.md](companies/Figure.md) | Figure(未上市) | 美国人形头号挑战者 |

### 📂 节奏工具
| 文件 | 内容 |
|---|---|
| [calendar.md](calendar.md) | 周度 / 月度 / 季度领先指标日历 |

### 📂 从业 / 职业(独立目录,非投资视角)
> 已迁出至 [`../embodied_ai/`](../embodied_ai/) — 给"考虑跳槽到具身智能领域"的从业视角内容。

---

## 二、机器人板块全景图

```
┌─────────────────────────────────────────────────────────────────┐
│                    机器人板块整体地图                              │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  人形(故事) │  │  医疗(成熟) │  │  仓储(订单) │  │  工业(周期) │
│              │  │              │  │              │  │              │
│ TSLA Optimus │  │ ISRG da Vinci│  │   SYM        │  │   TER UR     │
│ Figure       │  │ SYK Mako     │  │   SERV       │  │   ROK        │
│ 1X NEO       │  │ MDT Hugo     │  │   AutoStore  │  │   FANUY/YASKY│
│ Unitree      │  │ PRCT AquaBeam│  │   Locus      │  │   ABB        │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                  │                  │                  │
       └──────────────────┴────┬─────────────┴──────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │   零部件 / 价值量分布         │
                ├──────────────────────────────┤
                │ 执行器/伺服  30-40%          │
                │ 减速器/丝杠  15-20% (卡脖子) │
                │ 灵巧手       10-15% (差异化) │
                │ 传感器        5-10% (AI 入口)│
                │ 结构件/电池/线缆 余下         │
                └──────────────┬──────────────┘
                               │
       ┌───────────────────────┴───────────────────────┐
       │                                                │
┌──────▼──────┐  ┌──────────────┐  ┌──────────────────▼────┐
│   AI 大脑    │  │   算力 / 芯片 │  │      软件 + 仿真        │
│              │  │              │  │                        │
│ NVIDIA Groot │  │   NVDA       │  │  Isaac Sim / Omniverse │
│ Helix(Figure)│  │   Tesla D1   │  │  RBLX / Unity          │
│ Foundation   │  │              │  │  Cognex                │
│ Models       │  │              │  │                        │
└──────────────┘  └──────────────┘  └────────────────────────┘
```

---

## 三、按"上手难度 / 风险偏好"分组的标的池

### 🟢 稳健型(适合核心仓)
| 标的 | Ticker | 角色 |
|---|---|---|
| Intuitive Surgical | ISRG | 医疗龙头,持续复利 |
| NVIDIA | NVDA | AI 算力底座 |
| Symbotic | SYM | 仓储龙头(注意 Walmart 集中度) |
| Tesla | TSLA | 板块 β |
| Stryker | SYK | 骨科机器人 + 综合医疗 |
| Sony ADR | SONY | CIS + 综合 |

### 🟡 成长型(中等弹性)
| 标的 | Ticker | 角色 |
|---|---|---|
| Procept BioRobotics | PRCT | 中盘高成长 |
| Teradyne | TER | 协作机器人 + 半导体 |
| Cognex | CGNX | 机器视觉 |
| Hesai | HSAI | 激光雷达机器人受益 |
| Schaeffler | SCFLF | 丝杠 + 估值便宜 |
| Harmonic Drive | HSCDF / 6324.JP | 谐波垄断 |

### 🔴 高弹性 / 题材型(小仓位)
| 标的 | Ticker | 角色 |
|---|---|---|
| Allient | ALNT | 微型电机小盘 |
| Serve Robotics | SERV | 配送机器人 |
| 优必选 | 9880.HK | 港股纯人形 |
| Asensus Surgical | ASXC | 手术小盘 |
| MicroVision | MVIS | 激光雷达投机 |

### 🟣 ETF / 一篮子
| 标的 | Ticker |
|---|---|
| Global X Robotics & AI | BOTZ |
| ROBO Global | ROBO |
| iShares Robotics | IRBO |

---

## 四、研究使用建议

### 自上而下流程
1. **先看 [calendar.md](calendar.md)** — 知道本周该看什么
2. **板块情绪判断** — Tesla / NVIDIA 是否在涨,A 股 Tesla 概念是否异动
3. **进入对应赛道文件** — 判断该赛道当前热度
4. **进入公司深挖** — 决策具体标的
5. **写入 pool.jsonl** — 跟踪进观察池

### 自下而上流程
1. 看到某只票异动(如 SERV 涨停)
2. 在 INDEX 找到该票所属赛道
3. 读对应赛道文件 + 公司深挖
4. 判断是题材炒作还是基本面驱动

### 节奏判断
- **Q1 / Q3**:Tesla 财报后,板块 β 最高
- **Q2 / Q4**:医疗机器人(ISRG / SYK)财报相对独立
- **春节 + 五一前后**:A 股相关概念信号源最活跃
- **CES(1 月)、AI Day(预计 6-9 月)、GTC(3 月)**:三大行业节奏点

---

## 五、当前(2026-06)板块判断

1. **AI 板块拥挤度极高,机器人是首选承接方向**
2. **Tesla Optimus 进入"5K 量产兑现窗口"** — 信号决定板块强度
3. **零部件领先于整机** — 订单先兑现
4. **医疗机器人是不依赖人形故事的"防御 + 成长"双重配置**
5. **小心伪人形概念股** — 估值已透支,下半年容易杀题材

---

## 六、待补充的研究 / 下一步

- [ ] 给每篇赛道文件持续更新季度数据
- [ ] companies/ 下扩充 SYK / NVDA / Schaeffler 深挖
- [ ] 增加 `pool_robots.jsonl` 整合所有标的进观察池
- [ ] 建立 Optimus 节奏 Tracker(每周更新)
- [ ] 跟踪 Figure / 1X / Unitree IPO 进展专档
