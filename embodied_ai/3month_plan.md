# 12 周(3 个月)具身智能学习计划

> 更新日期:2026-06-10
> 假设:你是数据科学 / 量化背景,有 Python,但没碰过机器人 / RL / 大模型训练
> 目标:**12 周内做出 1-2 个有展示价值的 demo,并初步判断是否要全力转行**
> 时间投入:**每周 10-15 小时**(兼职探索,不脱离交易主线)

---

## 一、12 周整体路线图

```
Week 1-2  ─→  打基础:Linux / PyTorch / 仿真环境
Week 3-4  ─→  跑通第一个 demo:LeRobot + 简单任务
Week 5-6  ─→  深入学习:RL 基础 + VLA 模型
Week 7-8  ─→  ⭐ 项目 A:模仿学习 / VLA 复现
Week 9-10 ─→  ⭐ 项目 B:RL + Sim2Real
Week 11   ─→  写博客 / 录视频 / GitHub polish
Week 12   ─→  网络 + 简历 + 决策
```

### 核心原则
1. **做项目 > 看视频** — 80% 时间在动手,20% 时间在补理论
2. **GitHub 公开** — 每个项目 commit 到公开仓库,这是简历素材
3. **每周输出**:周报(写在 GitHub 或 blog),建立"输出习惯"
4. **不追求看完所有论文** — 选择性深读 5-10 篇即可
5. **遇到卡点不超过 1 天** — 用 Claude / Discord / Stack Overflow 突破

---

## 二、Week 1-2:打基础(每周 10-12h)

### 目标
建立"机器人 ML 工程师"的工作环境和心智模型

### 任务清单

#### 环境搭建
- [ ] 装好 Linux(WSL2 或双系统或 Mac)
- [ ] CUDA + PyTorch 验证可用(若有 NVIDIA GPU,否则用 Colab / Lambda)
- [ ] Conda / uv 包管理
- [ ] VSCode + Python 插件 + Copilot
- [ ] Git + GitHub 账号,创建 `robotics-journey` repo

#### 必读 / 必看(总共 ~15h)
- [ ] **Sergey Levine CS285 Deep RL 课程** — 看前 5 节(Lecture 1-5),建立 RL 直觉
  - https://rail.eecs.berkeley.edu/deeprlcourse/
- [ ] **Lex Fridman 播客**:Sergey Levine、Pieter Abbeel、Karol Hausman 各 1 集
- [ ] **PyTorch 60-min Tutorial**(快速回顾,你应该已有基础)
- [ ] 读论文:**RT-2**(精读)+ **OpenVLA**(略读)

#### 动手任务
- [ ] 在 PyTorch 里实现一个简单 MLP + 训练 MNIST(15 分钟,热身)
- [ ] 跑通 **HuggingFace LeRobot** quickstart:
  - https://github.com/huggingface/lerobot
  - 跑通 PushT 任务(2D 模拟环境)
- [ ] 安装 **MuJoCo** + 跑 Gym 标准环境(CartPole、Humanoid)

### Week 1-2 交付物
- [ ] GitHub repo `robotics-journey` 创建,有 README
- [ ] LeRobot PushT demo 跑通,截图放 README
- [ ] 第一篇周报:"我对机器人学习的初印象"

---

## 三、Week 3-4:第一个 demo(每周 12-15h)

### 目标
跑通一个**完整的模仿学习 pipeline**,理解"数据 → 模型 → 评估"全流程

### 任务清单

#### 必读
- [ ] 论文:**Diffusion Policy**(Chi et al., 2023)— 精读
- [ ] 论文:**ALOHA**(2023)— 远程操作 + 模仿学习经典
- [ ] HuggingFace LeRobot 文档全部过一遍

#### 动手任务
- [ ] 用 LeRobot 训练一个 **Diffusion Policy**(在 PushT 任务上)
- [ ] 用 LeRobot 跑 **ACT(Action Chunking Transformer)** 在 Aloha 任务
- [ ] **可选实机**:如果预算允许,买一对 SO-100 机械臂($200/台,LeRobot 推荐)做真实遥操作
- [ ] 不买实机的备选:用 **MuJoCo MPL hand** 或 **Robosuite** 仿真

#### 理解层面
- [ ] 写一篇博客:"Diffusion Policy 怎么把动作生成变成扩散问题"
- [ ] GitHub 上 fork LeRobot,做一个小 PR(改个 typo 都行,熟悉协作)

### Week 3-4 交付物
- [ ] 1 个完整训练好的 Diffusion Policy 模型(权重 + 视频)
- [ ] 第二篇博客 / 周报
- [ ] LeRobot 仓库 1 次 PR(可以是文档级别)

---

## 四、Week 5-6:深入 RL + VLA(每周 12-15h)

### 目标
理解"大模型 + 机器人"的核心范式,为做项目 A 打底

### 任务清单

#### 必读论文(精读 + 笔记)
- [ ] **PPO**(Schulman 2017)— RL 基础算法
- [ ] **RT-1**(Google 2022)— 真实数据 Transformer
- [ ] **RT-2**(2023)— 你 Week 1 略读过的,这次精读
- [ ] **OpenVLA**(2024)— 开源细节
- [ ] **Pi-0**(Physical Intelligence 2024)— 商业级 VLA
- [ ] **Helix**(Figure 2025)— 工业落地版

#### 课程 / 视频
- [ ] CS285 看完后 5 节(Lecture 6-10)
- [ ] Sergey Levine 在 RSS 2024 的 keynote 视频
- [ ] Chelsea Finn 关于 imitation learning 的演讲

#### 动手任务
- [ ] **跑通 OpenVLA 的 inference**:
  - https://github.com/openvla/openvla
  - 用预训练模型在 simulator 跑几个任务
- [ ] **跑通 Pi-0 inference / 微调**(若代码可获取)
- [ ] 用 IsaacLab 或 Stable Baselines3 训练一个 PPO 在 Pendulum / HalfCheetah

### Week 5-6 交付物
- [ ] 5-6 篇论文笔记(可放 GitHub /notes 或 Notion)
- [ ] OpenVLA inference demo 视频
- [ ] PPO 训练曲线 + 视频

---

## 五、Week 7-8:⭐ 项目 A — VLA 微调实战(每周 12-15h)

### 目标
**做 1 个有展示价值的 VLA 微调项目**,作为面试时的"我会做什么"证据

### 项目方案(三选一)

#### 选项 A1:OpenVLA 自定义任务微调(推荐)
- 用 LIBERO 数据集或自建小数据集
- 微调 OpenVLA-7B 在新任务上
- 评估指标:成功率、泛化性
- 写完整 README + 分析

#### 选项 A2:Diffusion Policy 在新场景应用
- 用 Robosuite / RoboMimic 数据
- 改进 Diffusion Policy 架构(加 condition / 加 hint)
- 对比 baseline

#### 选项 A3:LeRobot ACT 改进
- 在 Aloha 数据上,改 ACT 的某个组件
- 量化改进效果

### 推荐选 A1
- 最贴近行业前沿
- "我微调过 OpenVLA"是简历亮点
- HuggingFace + LeRobot 社区可以求助

### 任务清单
- [ ] 选定数据集,理解格式
- [ ] 跑通基线
- [ ] 实验改进
- [ ] 训练曲线 + 评估
- [ ] 写完整技术 blog
- [ ] GitHub README polish + 视频 demo

### Week 7-8 交付物
- [ ] 1 个有完整 README、demo、视频的 GitHub 仓库
- [ ] 1 篇技术博客(发在 Medium / 个人博客 / 知乎)
- [ ] 项目可以放 LinkedIn 顶部 Featured

---

## 六、Week 9-10:⭐ 项目 B — RL + Sim2Real(每周 12-15h)

### 目标
做一个**纯 RL + 仿真**项目,锻炼"训练大量轮次 + sim2real"思维

### 推荐项目:NVIDIA Isaac Lab 训练人形步行

#### 任务
- [ ] 安装 Isaac Lab(2024 年开源,NVIDIA 推荐平台)
  - https://github.com/isaac-sim/IsaacLab
- [ ] 跑通 Isaac Lab 自带的 humanoid 训练 demo
- [ ] 修改 reward function,得到不同步态
- [ ] 域随机化(domain randomization)实验
- [ ] 训练曲线对比 + 视频

#### 进阶
- [ ] 用 Genesis(2024 末新出的高速仿真)对比 Isaac
- [ ] 试图做一个"机器狗 sim2real"(若有真机)

### 替代项目(若 Isaac Lab 跑不通)
- 用 MuJoCo MJX 训练 Humanoid
- 用 Brax(Google 的 JAX 仿真)

### Week 9-10 交付物
- [ ] Isaac Lab / MuJoCo 训练视频
- [ ] 实验对比报告
- [ ] 项目放 GitHub,polish README

---

## 七、Week 11:输出 + 网络(每周 8-10h)

### 目标
把前 10 周的成果**变成简历素材 + 行业 network**

### 任务清单

#### 内容输出
- [ ] **写综述博客**:"我作为量化转行者,3 个月学习具身智能的体会"(英文版 + 中文版)
- [ ] 做 1 个 5-10 分钟 YouTube / B 站视频展示项目
- [ ] LinkedIn 发文 + GitHub README 更新

#### 简历 / LinkedIn
- [ ] 简历加上 robotics 项目部分(放最前面)
- [ ] LinkedIn headline:"Quantitative Researcher → Robotics / Embodied AI"
- [ ] 把 GitHub link、博客 link、demo video 都放在 LinkedIn

#### 网络
- [ ] 联系 PI / Galbot / Figure / NVIDIA / 智元各 2-3 名现员工
  - LinkedIn DM:"我是从量化转行,做了一些 robotics 项目,想聊聊职业方向"
  - 期望反馈率 5-10%(很正常)
- [ ] 加入 1-2 个相关 Discord(LeRobot、HuggingFace Robotics、CoRL)
- [ ] 国内:加入"具身智能交流群"(知乎 / 微信)

#### 信息核对(下一阶段策划)
- [ ] 核对各家公司目前在招岗位
- [ ] 列出 5 家"我下个阶段重点投递"的目标公司

### Week 11 交付物
- [ ] 1 篇综述博客
- [ ] 1 个 demo 视频
- [ ] 简历 / LinkedIn 全更新
- [ ] 5+ 行业 networking 联系建立

---

## 八、Week 12:决策 + 下一阶段规划(每周 5-8h)

### 目标
**决定下一步**:是全力转行,还是继续兼职探索,还是放弃?

### 任务清单

#### 自我评估(诚实回答)
- [ ] 这 3 个月做项目时,我**真的爱做**还是只是"完成任务"?
- [ ] 我对 VLA / RL / Robotics 哪个最感兴趣?
- [ ] 我的项目跑出来时,有没有"哇这个真酷"的瞬间?
- [ ] 我愿意接受"前 1-2 年薪资可能不如交易"吗?
- [ ] 我跟交易事业的精力分配能 50/50 吗?还是必须二选一?

#### 决策树
```
项目做的开心,有兴趣 ──→  全力转行(下一阶段:投简历 + 面试)
项目做完不讨厌,但不算热爱 ──→  继续兼职 6 个月,做更深 project
项目做得痛苦 ──→  放弃,继续做交易(也是有效结论!)
```

#### 如果选"全力转行"
- [ ] 制定下一个 3 个月的求职 / 深化计划
- [ ] 内推渠道梳理
- [ ] 准备面试(LeetCode + ML 面经)

#### 如果选"继续探索"
- [ ] 列出下 3 个月想深入的方向(灵巧手 / 触觉 / 长程任务等)
- [ ] 找 1 个开源项目长期贡献

### Week 12 交付物
- [ ] 自我评估 + 决策文档(写给自己看)
- [ ] 下一阶段计划

---

## 九、关键资源清单(整个 12 周用)

### 课程(免费)
| 资源 | 链接 | 优先级 |
|---|---|---|
| **CS285 Deep RL**(Sergey Levine) | https://rail.eecs.berkeley.edu/deeprlcourse/ | ⭐⭐⭐⭐⭐ |
| **CS287 Advanced Robotics**(Pieter Abbeel) | UC Berkeley | ⭐⭐⭐⭐ |
| **MIT 6.832 Underactuated Robotics**(Russ Tedrake) | underactuated.mit.edu | ⭐⭐⭐ |
| **Stanford CS224R**(Chelsea Finn,2024) | YouTube | ⭐⭐⭐⭐ |
| **HuggingFace LeRobot 教程** | https://huggingface.co/blog/lerobot | ⭐⭐⭐⭐⭐ |

### 仿真平台(必装至少 2 个)
| 平台 | 用途 | 学习曲线 |
|---|---|---|
| **MuJoCo / MJX** | 经典物理仿真 | 中 |
| **Isaac Lab / Sim** | NVIDIA,GPU 加速 | 中-高 |
| **Genesis**(2024 末)| 超高速,新 | 中 |
| **Robosuite** | 操作任务专用 | 低 |
| **PyBullet** | 老牌但简单 | 低 |

### 代码仓库(必 Star 必读)
- [LeRobot](https://github.com/huggingface/lerobot) — HuggingFace 标杆
- [OpenVLA](https://github.com/openvla/openvla) — 开源 VLA
- [Isaac Lab](https://github.com/isaac-sim/IsaacLab) — NVIDIA 仿真
- [Diffusion Policy](https://github.com/real-stanford/diffusion_policy)
- [Stable Baselines3](https://github.com/DLR-RM/stable-baselines3) — RL 算法

### 论文必读 Top 10(按时间)
1. PPO(2017)— Schulman
2. SAC(2018)— Haarnoja
3. RT-1(2022)— Google
4. RT-2(2023)— Google
5. Diffusion Policy(2023)— Columbia
6. ALOHA(2023)— Stanford
7. OpenVLA(2024)— Stanford
8. Pi-0(2024)— Physical Intelligence
9. Helix(2025)— Figure
10. Groot N1(2025)— NVIDIA

### 社区(必加)
- HuggingFace Discord(LeRobot 频道)
- LinkedIn:follow Sergey Levine、Chelsea Finn、Karol Hausman、王鹤
- Twitter/X:@chelseabfinn、@svlevine、@DrJimFan、@physical_int、@1x_tech、@Figure_robot
- 中国:机器之心交流群、知乎"具身智能"话题、微博 / 微信"具身智能 + 北大"群

---

## 十、预算 + 硬件建议

### 必需(预算 ~$0-500)
- 你电脑(Mac 或 Linux)— 已有
- Colab Pro($10/月)或 Lambda Cloud(按需)— GPU 训练
- 论文订阅:arxiv 免费

### 推荐(预算 ~$500-2000)
- **SO-100 机械臂**($200-400/台)— LeRobot 推荐,真机调试
- **本地 RTX 4090 / 5090**($1500-2000)— 大量训练
- **入门级双臂套件**($1000-2000)

### 不必需
- 高端机器人(Spot 等)
- 工业级激光雷达
- 真人形机器人

> **重点**:仿真 + Colab 就能完成 80% 学习,不要在硬件上一开始花太多钱

---

## 十一、每周时间分配建议

```
周一 ─→ 1.5h 看论文 / 课程
周二 ─→ 2h 写代码(项目)
周三 ─→ 1h 看论文 / 课程
周四 ─→ 2h 写代码(项目)
周五 ─→ 0.5h 整理本周笔记
周六 ─→ 4-6h 集中开发(深度工作时段)
周日 ─→ 1h 写周报 + 网络(LinkedIn / Discord)

总计:约 12-15h/周
```

### 兼顾交易主线
- **早晨开盘前** 1 小时:仍按你目前的 watchlist / pool.jsonl 做交易研究
- **盘中** 不动,做交易
- **晚上 / 周末**:robotics 学习
- **不要混合时段** — 切换成本高

---

## 十二、应对挫折的"心理预案"

### 必然会遇到的卡点
| 卡点 | 应对 |
|---|---|
| LeRobot 装不上 / 跑不通 | 卡 1 天找不出就发 Discord / GitHub Issue |
| 论文看不懂 | 跳过,先看代码,看完再回来 |
| 训练效果差 | 完全正常,行业里 90% 实验都是失败的 |
| 觉得自己"啥都不会" | 这是 imposter syndrome,所有人都经历 |
| 时间不够 | 优先项目 A,放弃项目 B 也行 |
| 对兴趣不确定 | Week 12 才决定,不要中途 |

### 关键认知
- **3 个月不够"成为专家"**,但**够判断"我适不适合"**
- **80% 的 ML 实验是失败的**,这是正常的
- **行业标杆都是 5-10 年积累**,不要自我对比

---

## 十三、12 周后,你应该有的"凭证"

简历上能写:

> **Robotics & Embodied AI(Self-directed, 2026.06 - 2026.09)**
> - Reproduced and fine-tuned OpenVLA on custom dataset
> - Trained Diffusion Policy on PushT and Aloha tasks
> - Implemented PPO-based humanoid control in Isaac Lab
> - Contributed to LeRobot open-source project
> - Published 3+ technical blog posts on VLA / RL / Sim2Real
> - GitHub: github.com/yourname/robotics-journey

这份履历**比 80% 的"想转行"候选人扎实** — 因为你做了真实项目,有公开输出。

---

## 相关文件
- 全景:[primer.md](primer.md)
- 自我评估:[gap_analysis.md](gap_analysis.md)
- 目标公司:[target_companies.md](target_companies.md)
