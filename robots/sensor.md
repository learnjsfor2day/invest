# 传感器 深度分析

> 更新日期:2026-06-10
> 行业地位:机器人的"五感",AI 时代价值量上升最快的环节

---

## 一、机器人传感器架构

机器人需要五类感知:

| 类型 | 用途 | 部位 | 类比 |
|---|---|---|---|
| **视觉** | 环境感知 | 头部、胸部 | 眼睛 |
| **力矩 / 力觉** | 操作反馈 | 关节、手腕 | 触觉(深) |
| **触觉** | 表面感知 | 指尖、掌面 | 触觉(浅) |
| **IMU / 惯性** | 姿态平衡 | 躯干、四肢 | 内耳前庭 |
| **听觉 / 雷达 / 激光** | 远距离感知 | 头部、胸部 | 耳朵 + 第六感 |

> **关键认知**:AI 大模型需要"高质量数据",传感器是数据入口。**传感器决定 AI 能学到多少**,所以这是 AI 时代价值量上升最快的零部件。

## 二、各类传感器深度

### 1. 视觉(摄像头 + 深度感知)

**技术路线**:
- RGB 摄像头(主流)
- 立体相机(Intel RealSense、Stereolabs)
- 结构光(早期 Kinect)
- ToF(Time-of-Flight,iPhone LiDAR 类)
- 事件相机(Event Camera,Prophesee)— 新兴
- **激光雷达**(L4 自动驾驶级别,Optimus 不用,但仓储/服务机器人用)

**玩家**:
- Sony (6758.JP) — CMOS 图像传感器全球第一(50% 份额)
- ON Semiconductor (ON) — 第二
- OmniVision(韦尔股份 603501.SH 旗下)— 第三
- Prophesee(法国,事件相机)— 未上市
- Intel RealSense — 内部产品线
- Mobileye (MBLY) — 视觉 AI

### 2. 力矩传感器(Force/Torque Sensor)

**作用**:让机器人"知道用了多大力气",是协作机器人的安全核心、灵巧手抓取的关键。

**技术**:
- 应变片(Strain gauge)— 主流
- 光学(光纤光栅)— 高端
- 电容 — 新兴

**玩家**:
- ATI Industrial Automation(美国,被 Novanta 收购)
- Schunk(德国)
- Bota Systems(瑞士)
- 柯力传感(603662.SH)— 中国
- 鸿洁科技、汉威科技 — 中国
- **国内人形供应链兴起后,力矩传感器爆发性最强**(单台 5-7 个,单价 $200-500)

### 3. 触觉传感器(Tactile Sensor)

**这是 AI 机器人时代最大增量**

**技术路线**:
| 路线 | 原理 | 玩家 |
|---|---|---|
| **电阻式** | 压敏电阻 | 多数低端方案 |
| **电容式** | 电容变化 | Tekscan、Pressure Profile |
| **光学(视触觉)** | 摄像头看变形 | GelSight、Meta Digit、Sony FingerTPS |
| **MEMS 阵列** | 微机械感知 | XELA Robotics(日本)|

**重点公司**:
- **GelSight**(MIT 系)— 未上市,视触觉技术领先
- **Meta** — 内部 Digit 触觉传感(开源硬件)
- **Sony** — FingerTPS
- **XELA Robotics**(日本)— 商用触觉阵列
- 帕西尼感知(中国)— 国产视触觉
- Nidec、Murata — 综合电子厂跟进

### 4. IMU / 姿态传感器

**作用**:陀螺仪 + 加速度计,机器人保持平衡核心。手机里也有,但机器人级精度高 100 倍。

**玩家**:
- **STMicroelectronics (STM)** — 全球 MEMS 老大
- **Bosch Sensortec** — 私有
- **InvenSense / TDK** — TDK 旗下
- **Honeywell** — 高端航空级
- **Analog Devices (ADI)** — 高精度
- 矽睿、明皜 — 中国

### 5. 激光雷达 / 毫米波雷达 / 超声(扩展感知)

**用途**:仓储、服务机器人需要;**人形机器人 Optimus 路线不用激光雷达,只用纯视觉**(Tesla 哲学)。但其他人形(Boston Dynamics、Apptronik、1X)仍用 LiDAR。

**玩家**:
- **Ouster (OUST)** — 工业激光雷达
- **Hesai (HSAI)** — 中国激光雷达,机器人订单多
- **Luminar (LAZR)** — 偏汽车
- **MicroVision (MVIS)** — 投机性强
- **Innoviz (INVZ)** — 偏汽车

## 三、可交易标的(美股优先,按价值量排)

### 视觉传感器

| 公司 | Ticker | 说明 |
|---|---|---|
| **Sony** | SONY | CIS 全球第一,机器人视觉受益 |
| **ON Semiconductor** | ON | 第二大 CIS |
| **Mobileye** | MBLY | 视觉 + AI 芯片 |
| **Cognex** | CGNX | 工业机器视觉 |
| **Teledyne** | TDY | 工业相机 + 红外 |
| **FLIR(Teledyne 旗下)** | TDY | 红外 |
| **Lumentum** | LITE | 3D 感知激光 |

### 激光雷达

| 公司 | Ticker | 说明 |
|---|---|---|
| **Hesai** | HSAI | 中国龙头,机器人订单多 |
| **Ouster** | OUST | 工业 + 仓储应用强 |
| **Luminar** | LAZR | 汽车为主 |

### 力矩 / 触觉 / IMU(纯标的少)

| 公司 | Ticker | 说明 |
|---|---|---|
| **STMicroelectronics** | STM | MEMS / IMU |
| **Analog Devices** | ADI | 高端 IMU + 信号链 |
| **TDK** | TTDKY | InvenSense IMU |
| **Honeywell** | HON | 高精度 IMU |
| **Methode Electronics** | MEI | 触觉/力觉 |
| **Novanta** | NOVT | 收购 ATI 后含力矩 |

### 综合传感器(机器人 + 工业)

| 公司 | Ticker | 说明 |
|---|---|---|
| **Amphenol** | APH | 连接器 + 传感综合 |
| **TE Connectivity** | TEL | 同上 |
| **Sensata** | ST | 综合传感 |

### 中国(高弹性,流动性差)

| 公司 | Ticker | 看点 |
|---|---|---|
| 韦尔股份 | 603501.SH | OmniVision CIS |
| 柯力传感 | 603662.SH | 力矩 |
| 汉威科技 | 300007.SZ | 力觉/嗅觉 |
| 奥比中光 | 688322.SH | 3D 视觉 |
| 速腾聚创 | 02498.HK | 激光雷达 |

## 四、关键技术趋势

### 趋势 1:视觉 AI 替代部分硬件
- 大模型让单纯 RGB 图像就能估计深度、力度
- 这会**侵蚀部分专用传感器需求**(深度相机、低端力矩)
- 但**反过来增加触觉传感器需求**(因为 AI 需要"真触觉"训练)

### 趋势 2:多传感器融合(Sensor Fusion)
- 单一传感器不够,机器人需要 AI 融合 RGB + 触觉 + IMU
- 这要求标准化 SDK / 数据格式 — 利好平台型公司(NVIDIA Isaac)

### 趋势 3:边缘 AI 芯片下沉
- 传感器内置 AI(Smart Sensor)
- 利好:Sony(把 AI 直接做进 CIS)、ADI(智能传感+AI)

### 趋势 4:数据飞轮 + 触觉爆发
- 谁有触觉数据,谁能训练更聪明的灵巧手
- Tesla / Figure / Meta 都在加大投入
- **触觉传感器是 2026-2028 的"下一个激光雷达"**

## 五、领先指标

### 战略级
1. **Sony / ON / OmniVision CIS 季度出货数据**
2. **大厂触觉传感器收购**(过去 5 年频繁,如 Meta 收 Ctrl-Labs、Tesla 收 SciSparc 传闻)
3. **Tesla 是否引入激光雷达**(标志路线分歧)

### 战术级
4. **OUST / HSAI 季度订单中机器人客户占比**
5. **A 股视觉/传感器板块走势**
6. **MEMS 行业月度报告**(Yole 发布)

### 节奏级
7. **CES、SensorsExpo、Embedded World** 新品
8. **学术会议触觉论文(ICRA、IROS)发布数**

## 六、当前(2026-06)判断

1. **CIS(图像传感器)是最稳健的"机器人信号"** — Sony / ON 都受益
2. **激光雷达分化**:Ouster 工业 / Hesai 机器人 在涨,Luminar / Innoviz 偏汽车承压
3. **触觉传感器是最大题材增量**,但目前美股没有纯标的 — 关注 Meta 是否拆分、GelSight IPO
4. **力矩传感器 A 股弹性最大**(柯力传感、汉威科技)
5. **STM、ADI 是稳健配置**,人形是 catalyst 之一不是全部

## 七、组合 framing

| 仓位 | 标的 | 理由 |
|---|---|---|
| 核心稳健 | Sony (SONY) / STM | CIS + MEMS 龙头 |
| 工业感知 | Cognex (CGNX) / Teledyne (TDY) | 机器视觉 |
| 激光雷达弹性 | Hesai (HSAI) / Ouster (OUST) | 机器人订单兑现 |
| 综合 | Amphenol / TE Connectivity | 综合传感 + 连接器 |
| 题材投机 | A 股力矩/触觉概念股 | 短线 |

## 八、未解决的研究问题

- [ ] Tesla Optimus 视觉传感器是否仍来自 Sony(供应商关系)
- [ ] 触觉传感器何时出现"标准件"——决定是否能规模化
- [ ] GelSight 商业化路径(独立 vs 被收购)
- [ ] 视觉 AI 是否真能完全替代力矩传感器(行业争议)
- [ ] Hesai 在人形机器人订单具体占比
- [ ] 激光雷达在仓储 / 服务机器人 vs 人形机器人的渗透差异
