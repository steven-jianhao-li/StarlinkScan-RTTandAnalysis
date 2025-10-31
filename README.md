# StarlinkScan-RTTandAnalysis

一个用于采集并分析网络往返时延（RTT）的工具集，包含“两个点对比（pair）”与“面向大量 IP 的大规模扫描（mass）”两种模式，并集成基础的自动分析与可视化能力。

## 体系结构概览

- main.py：统一入口，提供模式选择与流程编排
  - pair：按配置文件对目标进行周期性 ICMP/DNS 探测，生成 JSONL；自动完成两点分析
  - mass-scan：读取带有地面/卫星分组的目标清单，按 IP 输出 CSV（ground 与 satellite 分目录存放）
  - analyze-pair：对 pair 模式的某次任务目录进行分析
  - analyze-mass：对 mass 扫描结果目录进行分析
- src/collection/*：探测器
  - IcmpCollector：使用 ping3 采集 ICMP RTT
  - DnsCollector：DNS 查询 RTT
  - RdnsCollector / TracerouteCollector：一次性补充元数据（pair 模式）
- src/analysis/*：分析器
  - pair_rtt_analyzer.py：两点分析，输出统计、图像与 K-S 检验结果
  - mass_rtt_analyzer.py：大规模结果分析（支持 ground/satellite 标签）
  - plot_utils.py：绘图工具（自动图例，KDE 非负裁剪、直方图等）
- src/utils/*：配置与日志

## 运行模式与数据形态

### Pair（两点对比）
- 输出目录：`data/output/<timestamp>/`
- 产物：
  - `raw_data.jsonl`（逐条探测结果）
  - `config.ini`, `task.log`, `targets.txt`
  - `plots/`（时间序列、KDE、直方图、箱线图等）
  - `packet_loss.csv`, `descriptive_stats.csv`, `ks_test.json`

### Mass（大规模扫描）
- 输入：`data/input/mass_targets.txt`（分组格式）
  ```
  [ground]
  1.1.1.1
  8.8.8.8

  [satellite]
  203.0.113.1
  ```
- 输出：`data/output/mass/<timestamp>/`
  - `ground/` 与 `satellite/` 目录中各自按 IP 命名的 CSV：
    `timestamp,target_ip,probe_type,rtt_ms,status`
  - 分析输出：`summary_by_ip.csv`、`summary_by_label.csv`、`kde_by_label.png` 等

## 设计要点

- 任务目录命名：只使用时间戳（YYYYMMDDTHHMMSS），避免长目录名
- I/O 写入独立进程：
  - pair：写 `raw_data.jsonl`，元数据（rdns/traceroute）拆到 `meta/`
  - mass：每个 IP 一个 CSV，且 ground/satellite 分开写入，形成可复用的 ground truth
- 绘图：
  - 自动图例显示（优先按 probe_type 区分）
  - KDE 强制非负显示（clip/cut + xlim>=0）
  - 直方图、箱线图补充视角

## Mass 分析建议（方案蓝图）

以下是“全面、有效”的大规模分析思路蓝图，将作为后续功能迭代的依据：

1) 数据清洗与标注
- 合并 ground/satellite 两组 CSV，保留 `label ∈ {ground, satellite}`
- 仅使用 `status=success` 且 `rtt_ms>=0` 的样本进入 RTT 统计
- 记录每个 IP 的总探测数、成功数、丢包率

2) 基础统计与排序
- 按 IP 计算：count/mean/median/p95/min/max/loss_pct → `summary_by_ip.csv`
- 生成 TopN 榜单：
  - 最低平均 RTT 的 IP（潜在优选路径）
  - 最低 p95 的 IP（稳定性视角）
  - 最低丢包的 IP（可靠性视角）
  - 反向榜单（高延迟/高丢包）用于排错

3) 组间对比（ground vs satellite）
- 按组聚合：
  - `summary_by_label.csv`（count/mean/median/p95/loss_pct）
- 可视化：
  - KDE（按 label）比较分布差异（`kde_by_label.png`）
  - CDF（累计分布）比较；用于衡量“超过某阈值的比例”
  - 箱线图/小提琴图比较两组总体分布（含异常值）
- 统计检验：
  - 使用 Mann–Whitney U 或 KS 检验比较两组 RTT 分布（报告统计量与 p 值）

4) 空间/网络归因（可选增强）
- 通过 rDNS/Whois/GeoIP 为 IP 标注 ASN、国家/地区、城市
- 分组对比：按 ASN、国家、城市维度统计 mean/p95/loss_pct
- 产出“热力地图”或“国家/ASN 维度 TopN”榜单

5) 稳定性与尾部特征
- 计算每 IP 的方差、IQR、MAD，识别抖动大的主机
- 关注 p99、(p95-p50) 差值等尾部指标

6) 阈值与告警（可选增强）
- 定义 SLA 阈值（如 mean<50ms 且 loss<1%）
- 输出达标/不达标清单与原因

7) 输出制品与可视化（目录结构）
- `summary_by_ip.csv`、`summary_by_label.csv`、`topn_*.csv`
- `plots/`：
  - `kde_by_label.png`, `cdf_by_label.png`, `box_violin_by_label.png`
  - `mean_rtt_across_ips.png`, `mean_vs_loss_scatter.png`
  - `topn_bars.png` 等

## 后续开发计划（依据上面蓝图）
- mass_rtt_analyzer：
  - [ ] 增加 CDF、箱线图/小提琴图；引入组间统计检验（Mann–Whitney/KS）
  - [ ] 生成 TopN 榜单与相应柱状图
  - [ ] 可选 Geo/ASN 标注与分组统计
  - [ ] 统一输出到 `<timestamp>/plots/` 目录
- main：
  - [ ] mass-scan 增加并发与重试选项；可选 DNS 测量
- 数据：
  - [ ] 扩展 mass_targets.txt 支持注释别名，如 `ip # name`

## 快速开始

- 交互运行：
  ```bash
  python main.py
  ```
- 指定模式：
  ```bash
  # 两点扫描+分析
  python main.py --mode pair

  # 大规模扫描
  python main.py --mode mass-scan

  # 仅分析两点结果
  python main.py --mode analyze-pair --input data/output/<timestamp>

  # 分析大规模结果
  python main.py --mode analyze-mass --input data/output/mass/<timestamp>
  ```

如需调整参数，请编辑 `configs/default_config.ini`。
