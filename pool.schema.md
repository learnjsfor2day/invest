# pool.jsonl 字段说明

每行一条 JSON 记录,代表一家公司。Agent 可用 `pd.read_json("pool.jsonl", lines=True)` 一行加载。

## 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `ticker` | string | 主交易代码(美股优先);未上市公司用名称 slug |
| `name_en` | string | 英文名 |
| `name_zh` | string | 中文名 |
| `country` | string | ISO 国别 (US/CN/TW/KR/JP/NL/DE/CA/IL/AU/GB/FR/CH/IE/HK/NO/TH) |
| `exchange` | string | NASDAQ/NYSE/HKEX/TWSE/TPEx/KRX/TSE/SSE/SZSE/AEX/OTC/null |
| `listed` | bool | 是否上市 |
| `us_tradable` | bool | 能否在美股账户直接买(含 ADR) |
| `alt_tickers` | string[] | 其他上市地代码,如 `["9988.HK"]` |
| `tags` | string[] | 细分赛道(英文 snake_case,见下) |
| `chains` | string[] | 产业链层级(英文 snake_case) |
| `added` | bool | `true` = Claude 新补充,需人工 review |
| `notes` | string | 备注/说明 |

## chains(产业链层级,18 类)

- `ai_application` — AI 应用层(助手、企业软件、医疗、金融、安防、广告、自动驾驶、机器人)
- `foundation_models` — 大模型/基础模型层
- `cloud_compute` — 云服务/AI 训练推理平台
- `ai_chips` — AI 加速芯片
- `ai_pc_npu` — AI PC 芯片 / NPU
- `memory_storage` — HBM / DRAM / NAND / SSD / 企业存储
- `advanced_packaging` — 先进封装 / CoWoS / Chiplet
- `foundry` — 晶圆代工
- `semi_equipment` — 半导体设备
- `semi_materials` — 半导体材料
- `ai_servers` — AI 服务器整机 / 机柜 / ODM
- `pcb_connectors` — 主板 / PCB / 连接器 / 高速线缆
- `network_optical` — 网络芯片 / 交换机 / 光模块
- `power_distribution` — 电源 / UPS / 配电 / 变压器
- `cooling` — 液冷 / 散热 / 机房温控
- `datacenter_construction` — 数据中心建设 / REITs / 工程
- `ai_pc_devices` — AI PC / 终端硬件
- `energy_materials` — 能源 / 铜 / 稀土 / 通信材料

## tags 常用值(节选)

**应用层**: general_ai_assistant, enterprise_ai_software, coding_ai, ai_search, ai_creative, ai_healthcare, ai_finance_data, ai_defense_gov, ai_advertising, ai_security, ai_education, ai_communication, ai_automation, ai_observability, autonomous_driving, humanoid_robot, warehouse_robot, robot_surgery, voice_ai, llm_training_data, edge_ai, pure_ai_play

**模型**: closed_source_model, open_source_model, multimodal_model, enterprise_private_model, model_hub, data_labeling, vector_database, data_streaming, data_cloud

**云**: public_cloud, gpu_cloud, enterprise_cloud, china_cloud, datacenter_hyperscaler, crypto_to_ai_miner

**芯片**: gpu, asic_custom_chip, ai_inference_chip, ai_training_chip, edge_ai_chip, x86_ai_pc_chip, arm_ai_pc_chip, cpu_npu, npu_ip_architecture, fpga, mcu, analog, power_management_ic, sic_power, rf_chip, audio_chip, china_ai_chip, wafer_scale, eda

**存储**: hbm, dram, nand_ssd, hdd, enterprise_ssd_controller, memory_ip, ai_storage

**封装/代工**: advanced_packaging, cowos_supplychain, abf_substrate, glass_substrate, packaging_equipment, hybrid_bonding, leading_node_foundry, mature_node_foundry, ai_chip_foundry

**设备/材料**: lithography_euv, etch, deposition, ion_implant, cmp, cmp_material, cleaning, metrology_inspection, test_probe, silicon_wafer, photoresist, electronic_specialty_gas, wet_chemicals, sputtering_target, packaging_material

**服务器/连接**: server_brand, ai_rack, odm_ems, pc_odm, pc_brand, pcb, high_speed_connector, high_speed_cable, high_speed_cable_aec, backplane

**网络/光**: ethernet_switch_chip, nic_dpu, switch_equipment, optical_module, optical_chip_laser, cpo_silicon_photonics

**电源/冷却/数据中心**: ups_power_management, power_distribution_lv, transformer, gas_turbine, power_generation, grid_equipment, datacenter_infra, datacenter_liquid_cooling, cold_plate_cdu, datacenter_hvac, thermal_material, immersion_cooling_fluid, datacenter_reit, construction_engineering, datacenter_power

**能源/材料**: nuclear_power, smr, uranium, utility_power, natural_gas, fuel_cell, hydrogen, copper, rare_earth_magnet, optical_fiber_material, display_panel

## Agent 用法示例

```python
import pandas as pd
df = pd.read_json("pool.jsonl", lines=True)

# 只看美股可交易的 AI 应用层
us_apps = df[(df.us_tradable) & (df.chains.apply(lambda c: "ai_application" in c))]

# 找所有 GPU 标签的股票
gpus = df[df.tags.apply(lambda t: "gpu" in t)]

# 喂给 yfinance 批量拉数
import yfinance as yf
tickers = us_apps.ticker.tolist()
data = yf.download(tickers, period="1mo")

# 只看 Claude 新加的补充项,人工 review
df[df.added].to_csv("review_added.csv")
```

## 维护

- 新增公司:append 一行,`added=true` 标记
- 状态变更(IPO、退市、ADR 调整):更新 `listed`/`us_tradable`/`alt_tickers`
- 字段扩展:可加 `priority`(S/A/B/C)、`market_cap`、`watchlist_reason` 等,不影响已有 agent
