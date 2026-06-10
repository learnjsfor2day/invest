# 人形机器人 / 具身智能 全景介绍(从业视角)

> 更新日期:2026-06-10
> 视角:不只是投资,而是从业 — 技术栈、研究方向、公司、岗位、技能

---

## 一、术语先理清(行业里很多概念在混用)

| 术语 | 含义 | 关系 |
|---|---|---|
| **Robotics(机器人学)** | 50+ 年老学科,涵盖控制、运动学、机械、规划 | 大集合 |
| **Humanoid Robot(人形机器人)** | 仿人外形的机器人 | Robotics 的一个分支 |
| **Embodied AI(具身智能)** | AI + 物理身体,强调"通过身体与世界交互来学习/思考" | 思想,跨硬件 |
| **Embodied Intelligence(具身智能,中文常用)** | 同上,但在国内常等同于"通用人形机器人 + AI" | 偏产业 |
| **General-Purpose Robot(通用机器人)** | 不是为单一任务定制的机器人,人形是其形态之一 | 目标 |
| **Foundation Model for Robotics** | 机器人基础模型(VLA、VLM、World Model) | 当前主流方法 |

> **关键认知**:具身智能 ≠ 一定是人形。但**当前主流押注是"通用任务最好的形态是人形",所以行业重心都在人形**。学术界也有反对意见(轮式 + 机械臂可能更经济)。

---

## 二、技术栈全景(从下到上)

```
┌────────────────────────────────────────────────────┐
│   应用 / 任务层                                     │
│   家务、装配、护理、配送、巡检、手术辅助...           │
└────────────────────────────────────────────────────┘
                       ▲
┌────────────────────────────────────────────────────┐
│   高层规划(Task Planning)                          │
│   "把杯子放到桌上" → 子任务序列                      │
│   (LLM、HTN、PDDL、TAMP)                          │
└────────────────────────────────────────────────────┘
                       ▲
┌────────────────────────────────────────────────────┐
│   决策 / 推理(Reasoning)                          │
│   VLM 看场景 → 生成动作意图                          │
│   (GPT-4o、Gemini、Qwen-VL、Pi-0)                 │
└────────────────────────────────────────────────────┘
                       ▲
┌────────────────────────────────────────────────────┐
│   动作生成(Action Generation)                     │
│   ⭐ VLA 模型(Vision-Language-Action)              │
│   端到端:图像+指令 → 关节角度/力矩                  │
│   (RT-2、OpenVLA、Pi-0、Helix、Groot N1)          │
└────────────────────────────────────────────────────┘
                       ▲
┌────────────────────────────────────────────────────┐
│   底层运动控制(Motion Control)                    │
│   ⭐ "小脑":全身平衡、步态、阻抗控制                 │
│   (MPC、WBC、强化学习策略 RL Policy)               │
└────────────────────────────────────────────────────┘
                       ▲
┌────────────────────────────────────────────────────┐
│   感知 / SLAM(Perception)                         │
│   RGB-D、LiDAR、IMU、力矩、触觉 → 状态估计           │
│   (NeRF、Gaussian Splatting、3D 占据网络)          │
└────────────────────────────────────────────────────┘
                       ▲
┌────────────────────────────────────────────────────┐
│   硬件(Hardware)                                   │
│   骨架 + 执行器 + 灵巧手 + 传感器 + 电池 + 算力       │
└────────────────────────────────────────────────────┘
```

每一层都有岗位、有公司、有论文、有研究者。后面会逐层展开。

---

## 三、过去十年的范式变迁(必须搞懂)

### 阶段 1:经典控制(1990-2018)
- **代表**:Honda Asimo、Boston Dynamics Atlas(液压版)
- 思路:精确建模 → 求解最优控制
- 优点:可靠、可解释
- 缺点:**任何新任务都要工程师手工写**
- 学到的东西:运动学、动力学、ZMP 步态、MPC

### 阶段 2:深度强化学习(2018-2022)
- **代表**:OpenAI Dactyl(还原魔方)、ANYmal(腿足 RL)、Boston Dynamics 转电动 Atlas
- 思路:在仿真里 RL 训练 → sim-to-real 迁移
- 优点:不用手工建模,能学复杂技能
- 缺点:仿真现实差距大、训练慢、泛化差
- 学到的东西:PPO、域随机化、teacher-student

### 阶段 3:大模型 + 模仿学习(2022-2024)
- **代表**:Google RT-1 / RT-2、Diffusion Policy、ALOHA、Pi-0
- 思路:**用大量人类遥操作数据 + 大模型**直接学动作
- 关键论文:
  - **RT-1**(2022)— 真实数据机器人 Transformer
  - **RT-2**(2023)— 用 VLM 做动作生成,Google 标志作品
  - **OpenVLA**(2024)— 开源 7B 模型
  - **Pi-0**(2024,Physical Intelligence)— 商业级 VLA
  - **Diffusion Policy**(2023,哥伦比亚)— 用扩散模型做动作

### 阶段 4(我们正处的):基础模型 + 全身策略(2024-)
- **代表**:Helix(Figure)、Groot N1(NVIDIA)、Pi-0.5(PI)、Helix-π(Physical Intelligence)
- 思路:**Foundation Model for Robotics** — 像 GPT 一样,一个模型多任务
- 关键技术:
  - 双系统架构(System-1 慢思考 + System-2 快反应)
  - **遥操作数据 + 互联网视频 + 仿真**联合训练
  - 跨形态(Cross-embodiment)训练
  - 视频生成模型 → 动作

### 阶段 5(未来 3-5 年):World Model + 自主探索
- 关键词:World Model、Dreamer、Sora-for-robots
- 机器人有"想象力",在脑子里规划
- 标杆候选:Yann LeCun JEPA、David Ha World Models

---

## 四、当前最重要的技术问题(= 研究热点 = 工作机会)

### 1. 数据问题(行业第一痛点)
- **机器人没有"互联网"** — 不像 LLM 有 Common Crawl
- 数据来源四条路径:
  1. **遥操作**(人类操作员控制机器人)— 贵,但质量最高
  2. **视频学习**(从 YouTube 学)— 海量但 noisy
  3. **仿真 + sim-to-real** — 易扩展,但 reality gap
  4. **机器人自主探索** — 长期最有希望,目前最难
- **谁解决数据,谁就赢一半** — Tesla、Figure、Physical Intelligence、NVIDIA 都在解

### 2. 操作(Manipulation)远难于行走
- 走路在 2024 年基本"解决了"(腿足 RL)
- 但**抓取、双手协调、长程操作**仍极难
- 灵巧手 + 触觉 + AI 是核心战场

### 3. 长程任务(Long-horizon)
- "去厨房做一杯咖啡" — 涉及 10+ 个子任务
- 失败概率累积:每步 95% → 10 步 60%
- 解决路径:层次化 + LLM 规划 + 重新规划(replanning)

### 4. Sim-to-Real Gap
- 仿真里训得好,真机翻车
- 域随机化、SysID、数字孪生、real2sim2real

### 5. 触觉感知
- 视觉 + 力矩可以走很远,但**精细操作必须有触觉**
- 视触觉(GelSight)、电容、MEMS 阵列都在演进

### 6. 安全 + 可解释性
- 端到端 VLA 是黑盒,难以认证
- 工业 / 家庭部署需要安全保证
- 这是机器人比 LLM 更严苛的地方

### 7. 跨形态泛化(Cross-embodiment)
- 同一个模型能否驱动不同机器人(人形 vs 机械臂 vs 四足)
- Open X-Embodiment 项目(Google + 21 家学术联合)是先驱

---

## 五、关键论文 + 学术资源(入门必读)

### 必读基础
1. **"RT-2: Vision-Language-Action Models"**(Google 2023)— VLA 开山
2. **"OpenVLA"**(Stanford+ 2024)— 开源版,代码可跑
3. **"Pi-0"**(Physical Intelligence 2024)— 商业级
4. **"Diffusion Policy"**(Chi et al. 2023)— 扩散动作模型
5. **"Helix"**(Figure 2025)— 工业落地版
6. **"Groot N1"**(NVIDIA 2025)— 开源人形基础模型
7. **"Open X-Embodiment"**(2024)— 跨形态数据集

### 必读综述
- **"A Survey on Foundation Models for Robotics"**(2024)
- **"Survey on Embodied AI"**(2023+)
- **"Real-World Robot Learning"**(Sergey Levine)

### 必看会议(投论文 / 找方向)
- **CoRL**(Conference on Robot Learning)— **机器人学习首会**
- **ICRA**(IEEE 国际机器人会议)— 综合最大
- **RSS**(Robotics: Science and Systems)— 偏理论
- **IROS**(智能机器人国际会议)
- **NeurIPS / ICML / CVPR**(部分机器人 track)
- **Humanoids**(IEEE 人形专会)

### 学术明星实验室
- **Stanford** — Chelsea Finn(IRIS lab)、Karen Liu、Dorsa Sadigh、Jeannette Bohg
- **CMU** — Deepak Pathak、Abhinav Gupta、Chris Atkeson
- **MIT** — Pulkit Agrawal、Russ Tedrake、Sangbae Kim
- **UC Berkeley** — Sergey Levine、Pieter Abbeel、Ken Goldberg
- **Princeton** — Mengdi Wang、Karthik Narasimhan
- **Columbia** — Shuran Song(Diffusion Policy 一作)
- **NVIDIA Research** — Dieter Fox、Yuke Zhu
- **DeepMind** — Pierre Sermanet
- **清华、北大、上交、港中文** — 中国顶尖实验室

### 必关注的研究者(Twitter/X 跟一遍)
- @chelseabfinn(Chelsea Finn)
- @svlevine(Sergey Levine)
- @YukeZhu
- @karen_liu
- @drussellmd(Russ Tedrake)
- @pathak2206(Deepak Pathak)
- @physical_int(Physical Intelligence)
- @1x_tech / @Figure_robot / @Tesla_AI

---

## 六、公司全景(以"想去工作"的视角)

### 类型 A:专注人形整机厂(技术深、压力大)

| 公司 | 文化 / 工作体验 | 适合谁 |
|---|---|---|
| **Tesla(Optimus)** | 节奏极快,996,Musk 亲自管,资源多但官僚少 | 工程师,愿意拼 |
| **Figure** | 高估值压力,精英团队,工程文化强 | 已有名校 + 大厂背景 |
| **1X** | OpenAI 背景,挪威 + 美国双地,偏研究 | 学术派 + 工程派结合 |
| **Boston Dynamics** | Hyundai 旗下,经典工程文化,稳定 | 偏经典控制、机械工程 |
| **Apptronik** | Mercedes 投,德州奥斯汀,中型规模 | 工程师 + 想要平衡的人 |
| **Agility Robotics** | 已有商业部署,务实 | 工程交付型 |

### 类型 B:AI 模型 / 平台公司(纯 AI 工程师友好)

| 公司 | 关键产品 | 备注 |
|---|---|---|
| **Physical Intelligence (PI)** | Pi-0、Pi-0.5 VLA 模型 | 当前**最热的具身 AI 创业**,Sergey Levine 联合创始 |
| **Skild AI** | 通用机器人基础模型 | Deepak Pathak 创始 |
| **Covariant** | 工业拣选 AI | 已被 Amazon 收购大部分团队(2024) |
| **NVIDIA Robotics** | Isaac Sim、Groot 平台 | 平台型,稳定大厂 |
| **Google DeepMind Robotics** | Gemini Robotics、SIMA | 顶尖学术 + 工业结合 |
| **Toyota Research Institute** | Diffusion Policy 等 | 偏研究,氛围好 |

### 类型 C:中国玩家(中文圈机会多)

| 公司 | 备注 |
|---|---|
| **Unitree(宇树)** | 杭州,工程导向,性价比 |
| **智元机器人** | 国家队背景 |
| **银河通用 Galbot** | 北大 + Wang He 团队,学术派 |
| **傅利叶智能** | 上海,医疗康复人形起家 |
| **小米机器人** | 雷军亲自抓,资源多 |
| **小鹏 Iron** | 整车厂转型 |
| **星动纪元** | 清华系 |
| **跨维智能** | 清华系 |
| **Astribot** | 上海,工业人形 |

### 类型 D:核心零部件公司(细分赛道,门槛清晰)

- **执行器**:Maxon(瑞士,精密)、Allient(美)、汇川 / 鸣志(中)
- **灵巧手**:Shadow Robot(英)、Sanctuary AI(加)、因时机器人(中)
- **触觉**:GelSight(MIT 系)、XELA Robotics(日)、帕西尼(中)
- **仿真**:NVIDIA Isaac、CoppeliaSim、MuJoCo

### 类型 E:学术 / 研究机构(发论文,不商业化)

- **大学实验室**(见上节)
- **Toyota Research Institute(TRI)**
- **Allen AI**(部分机器人)
- **Microsoft Research**
- **Meta FAIR Embodied AI**

---

## 七、典型岗位(知道自己适合哪种)

### 1. Robotics Software Engineer(运动 / 控制)
- **做什么**:写 MPC、WBC、IK 解算、ROS 节点
- **要求**:控制理论、C++、ROS、机器人学
- **薪资**:美国 $180-300K,中国 50-150 万
- **适合**:机械 / 自动化 / 控制背景

### 2. Robot Learning / RL Engineer
- **做什么**:在 Isaac Sim / MuJoCo 里训 RL,sim2real
- **要求**:RL、PyTorch、仿真平台、PPO/SAC 等
- **薪资**:美国 $200-350K
- **适合**:ML 研究背景

### 3. ML Researcher(VLA / Foundation Model)
- **做什么**:模型架构、训练、评估
- **要求**:LLM 经验、Transformer、大规模训练
- **薪资**:美国 $250-500K+
- **适合**:DL/NLP 研究背景

### 4. Perception Engineer
- **做什么**:相机、深度、SLAM、3D 重建
- **要求**:CV、SLAM、点云、RGB-D
- **薪资**:美国 $180-280K
- **适合**:CV 背景

### 5. Hardware / Mechanical Engineer
- **做什么**:执行器设计、关节模组、热管理、装配
- **要求**:机械工程、SolidWorks、电机控制
- **薪资**:美国 $150-250K
- **适合**:机械专业出身

### 6. Teleoperation / Data Engineer(数据团队)
- **做什么**:遥操作平台、数据收集、标注
- **要求**:工程能力、对数据敏感
- **薪资**:美国 $150-250K
- **适合**:DevOps / Data Eng 背景
- **冷门但极核心** — 数据是行业第一瓶颈

### 7. Product / Application
- **做什么**:跟客户(BMW、Amazon)对接,定义场景
- **要求**:行业知识、沟通能力
- **薪资**:中等

### 8. Simulation Engineer
- **做什么**:数字孪生、域随机化、MJX/Isaac/Genesis 开发
- **要求**:图形学、物理仿真、并行计算

---

## 八、技能栈(如果你想 1-2 年内入行)

### 必备(无论哪个岗位)
- **Python** — 行业默认语言(科研 + 大模型)
- **PyTorch** — 深度学习
- **Linux + Docker** — 工程化基础
- **Git** — 协作
- **数学** — 线性代数、概率、优化

### 工程岗加分
- **C++ 11/14/17** — 控制层、ROS
- **ROS / ROS2** — 机器人操作系统
- **Real-time 编程** — 控制环路 1kHz
- **嵌入式**(MCU、CAN 总线、EtherCAT)

### Learning 岗加分
- **JAX**(Google / DeepMind 系)
- **Isaac Lab / MuJoCo / Genesis** — 仿真
- **强化学习实操**(SB3、CleanRL)
- **大模型微调**(LoRA、PEFT、FSDP)
- **VLM / VLA 论文复现能力**

### 学术加分
- **顶会论文**(CoRL、RSS、ICRA、NeurIPS)
- **开源贡献**(OpenVLA、LeRobot、Diffusion Policy)
- **博士 / 博士后**(对纯研究岗几乎必需)

### 全栈"机器人 ML 工程师"建议项目(可作为入行作品)
1. 在 MuJoCo / Isaac Sim 里训一个抓取策略,sim2real 到真机
2. 复现 OpenVLA 在自己的机械臂上
3. 用 ALOHA / GELLO 做遥操作 + 模仿学习
4. 上 LeRobot(Hugging Face)平台做完整 demo

---

## 九、入行路径建议(具体怎么进)

### 路径 A:有 SWE / ML 背景,转机器人
- **起点**:刷 ROS 教程 + Sergey Levine CS285 RL 课程 + 跑 OpenVLA 复现
- **目标岗位**:大厂(NVIDIA / Tesla / Figure)Robot Learning / Perception
- **时间线**:6-12 个月准备
- **加分**:开源贡献 + 1-2 个 demo 视频

### 路径 B:有大模型 / NLP 背景,转 VLA
- **起点**:看 RT-2 / OpenVLA / Pi-0 论文,理解机器人特性
- **目标岗位**:Physical Intelligence / Skild AI / Figure / Tesla 的 ML Researcher
- **优势**:大模型经验是行业稀缺的

### 路径 C:有控制 / 机械背景
- **起点**:补 Python + PyTorch,但保留控制论 + 机械优势
- **目标岗位**:Boston Dynamics / Apptronik / Tesla 的 Robotics Software Engineer
- **优势**:能从硬件到软件全栈

### 路径 D:学术读博 / 博士后
- **起点**:申请上述明星实验室 PhD / Postdoc
- **目标**:发顶会、做开源、毕业去顶级公司或自己创业
- **时间线**:5+ 年但回报巨大

### 路径 E:加入中小公司 / 创业
- **起点**:身边有靠谱的具身智能 startup,直接加入
- **优势**:成长快,股权
- **风险**:多数公司会死,选公司很重要

---

## 十、行业现状(2026 年我的判断)

### 在哪一档?
- **2017-2022**:积累期,主要是学术
- **2023-2024**:大模型注入,资本爆发
- **2025-2026**:**工程兑现期** — 进工厂、做 demo、真出货
- **2027-2029**:产能 / 商业化竞争
- **2030+**:消费 / 普及

### 今天进入的优势
- 技术尚未收敛 — 个人贡献空间大
- 公司还在快速扩张 — 招聘窗口
- 估值高 — 股权有想象力

### 风险
- 商业化兑现可能不如预期 — 部分公司会死
- 资本退潮可能让中小公司断粮
- 技术路径可能突变(如 World Model 取代 VLA)
- 工作压力大(Tesla、Figure 节奏极快)

### 选公司的几个 lens
1. **技术领先性** — 不要去走老路的公司
2. **数据 / 场景** — 是否有真实场景沉淀数据
3. **资金 + 投资人** — 至少 12-24 个月跑道
4. **创始人 / 技术团队** — 看背景和团队气场
5. **股权 / 现金** — 估值合理吗,vesting 怎么样

---

## 十一、值得跟踪的内容源(每周必刷)

### 论文 / 技术
- **arxiv.org**:cs.RO(机器人)、cs.LG(学习)
- **paperswithcode.com** robotics tag
- **The Robot Report** newsletter
- **Andrej Karpathy / Lex Fridman** 播客(会聊机器人)

### 一级市场 / 公司动态
- **The Information**(深度报道)
- **Bloomberg / WSJ** 机器人专题
- **Crunchbase**(融资)
- **TechCrunch Robotics**

### 中国
- **机器之心**、**量子位**、**新智元** 公众号
- **甲子光年**、**腾讯科技** 深度
- 知乎"机器人"、"具身智能"话题

### 社群
- Twitter/X — 关注上节的研究者
- **r/robotics**、**r/MachineLearning** Reddit
- Discord:LeRobot、HuggingFace Robotics、CoRL 群

---

## 十二、给你的具体建议(基于你当前是美股交易者)

### 优势
- ✅ 你已经对行业全景很熟(已写完 11 篇研究)
- ✅ 你能看懂资本市场逻辑 — 选公司 / 谈薪很有用
- ✅ 你知道哪些公司"看上去强 vs 真的强"

### 短板(假设)
- ❓ 是否有 ML / 工程背景?
- ❓ 是否有顶会论文 / 开源经验?
- ❓ 是否能写 Python / PyTorch?

### 短期(3 个月)行动建议
1. **明确目标岗位** — 是 SWE? Researcher? Product? 不同准备路径不同
2. **跑通 1 个 demo** — 比如 OpenVLA + LeRobot + 简单机械臂
3. **跟踪 5 家目标公司**(Figure、PI、NVIDIA、智元、Unitree),看招聘 / 文化
4. **建立行业 network** — 从 LinkedIn、Twitter 开始,加入相关 Discord
5. **决定是先在中国还是美国** — 路径完全不同

### 中期(6-12 个月)
- 选定 3-5 家目标公司,深度研究
- 完成 1-2 个有展示性的 project / GitHub 仓库
- 参加行业会议(CES、ICRA、CoRL)
- 评估自己的"差距清单":要不要先去过渡公司补足

### 关于交易和工作的关系
- **去机器人公司工作 ≠ 不能交易** — 但需要遵守内幕交易规则,自家公司股票有限制
- **作为从业者,你对板块的认知会从"故事"变"现实"** — 这对长期投资非常宝贵
- 不要因为自己进去就"All in 板块",反而要更清醒看缺陷

---

## 十三、未解决的问题(你可能也在思考)

- [ ] 我应该先去美国还是中国机会更好?
- [ ] 大公司(Tesla / Figure)vs 创业公司(PI / 智元)选哪个?
- [ ] 该不该先读个 PhD 提升门槛?
- [ ] 我现有的技能能直接用上的有多少?
- [ ] 我应该多久内做出决定?
- [ ] 跳进去多久才会看出"这条路对不对"?

---

## 相关文件
- 行业整体:[humanoid.md](humanoid.md)
- 玩家对比:[private_players.md](private_players.md)
- 中美格局:[china_vs_us.md](china_vs_us.md)
- 三家整机:[companies/TSLA.md](companies/TSLA.md) / [companies/Figure.md](companies/Figure.md)
