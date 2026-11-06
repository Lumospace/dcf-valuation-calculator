# DCF 估值计算器

把估值工作中在 Excel 里手工搭建的 DCF 模型参数化：输入假设即可得到企业价值、股权价值与每股价值区间，并导出可直接复核的 Excel 测算表。

适用于估值、投行、PE/VC 场景中的快速测算与敏感性分析，也用于演示"业务手工流程 → 工具化"的改造路径。

## 功能

- 企业自由现金流（FCFF）两段式模型：显性预测期 + 终值
- 终值口径可在界面切换：Gordon 永续增长 / 退出倍数（EV/EBITDA），支持期中 / 期末折现
- 双变量敏感性表：Gordon 模式下为 WACC × 永续增长率，退出倍数模式下为 WACC × 退出倍数；指标可切换每股价值 / 股权价值 / 企业价值
- 悲观 / 基准 / 乐观三档情景分析
- 从 SQLite 读取历史财务数据，自动清洗并反推估值假设
- 一键导出 Excel（估值结果、关键假设、预测明细、敏感性分析、情景分析 5 张表，含数字格式与冻结窗格）
- 56 个单元测试覆盖公式、边界条件、数据清洗、界面冒烟与导出格式

## 快速开始

```bash
pip install -r requirements.txt

# 可选：生成演示数据库（app 首次运行也会自动生成）
python scripts/build_sample_db.py

streamlit run app.py
```

浏览器打开 `http://localhost:8501`。

## 目录结构

```
dcf-valuation-calculator/
├── app.py                  # Streamlit 界面
├── dcf/
│   ├── model.py            # 估值引擎：预测、终值、折现、结果与风险提示
│   ├── sensitivity.py      # 敏感性表与情景分析
│   ├── data.py             # SQLite 检索、清洗、假设反推
│   ├── export.py           # Excel 多表导出与数字格式
│   ├── formatting.py       # 展示层数据整理（图表数据）
│   └── sample_data.py      # 演示数据生成（虚构公司）
├── scripts/
│   └── build_sample_db.py  # 生成样本数据库的 CLI
├── tests/                  # 单元测试
├── data/                   # 运行时生成的数据库（已 gitignore）
└── requirements.txt
```

## 模型口径

```
FCFF_t = EBIT_t × (1 - 税率) + 折旧摊销_t - 资本开支_t - ΔNWC_t
ΔNWC_t = (营业收入_t - 营业收入_t-1) × NWC/收入

TV       = FCFF_n × (1 + g) / (WACC - g)        # Gordon 永续增长
PV(TV)   = TV × 折现系数_n

EV       = Σ PV(FCFF_t) + PV(TV)
股权价值  = EV - 净负债
每股价值  = 股权价值 / 股本
```

- 折现时点：期中折现取 `t = 0.5, 1.5, 2.5…`，期末折现取 `t = 1, 2, 3…`
- 退出倍数法：`TV = 末年 EBITDA × 退出倍数`
- 收入增速在预测期内由首年水平线性收敛至末年水平（`fade_schedule`）

模型内置以下校验与提示，避免出现"看起来合理但假设不成立"的结果：

| 情形 | 处理 |
| --- | --- |
| WACC ≤ 永续增长率 | 直接报错，终值公式不成立 |
| 终值占 EV 超过 85% | 提示估值高度依赖永续假设 |
| WACC 与 g 差距不足 2 个百分点 | 提示终值不稳定 |
| 预测期自由现金流为负 | 提示需复核营运资本与资本开支 |
| 股权价值为负 | 提示净负债已超过企业价值 |

## 数据说明

`data/sample_financials.db` 中的 5 家公司（恒瑞智造、云启科技、华辰医药、明远消费、中港物流）均为**虚构样本**，仅用于演示，不代表任何真实企业。

数据清洗流程（`dcf/data.py::clean_financials`）：

1. 字段类型转换，非法值转为空值
2. 按年份去重，保留最后一条
3. 剔除营业收入缺失或非正的样本
4. 折旧摊销、资本开支、营运资本缺失时按中位数填补
5. 金额由万元换算为元、股本由万股换算为股
6. 派生收入增速与 EBIT 利润率，供假设反推使用

## 测试

```bash
python -m unittest discover -s tests -v
# 或
pytest tests -v
```

覆盖范围：

- 预测期收入复合、FCFF 公式、折现系数（用手算基准案例逐年核对）
- 终值公式、退出倍数法、WACC ≤ g 等边界条件
- 敏感性表单调性（WACC 升高则价值下降、g 升高则价值上升）与非法组合置空
- 退出倍数模式下的敏感性列、中心格与基准一致
- 情景排序、数据清洗规则、单位换算、Excel 工作表完整性与数字格式
- 图表数据无 NaN（防止索引对齐导致空图）
- 界面冒烟：样本 / 手动 / 退出倍数三种模式与非法参数下页面不崩溃

## Git 工作流

```bash
git init
git add .
git commit -m "feat: DCF 估值引擎与 Streamlit 界面"

git switch -c feature/exit-multiple
# ... 开发 ...
git switch main
git merge feature/exit-multiple
```

## 在线 Demo

<https://dcf-valuation-calculator.streamlit.app/>

公开仓库：<https://github.com/Lumospace/dcf-valuation-calculator>

## 部署到 Streamlit Community Cloud

1. 把仓库推送到 GitHub（免费额度要求仓库为 public）
2. 打开 <https://share.streamlit.io>，用 GitHub 账号登录
3. New app → 选择仓库与分支 `main` → 主文件填 `app.py` → Deploy
4. 首次启动会自动生成 `data/sample_financials.db`，无需额外配置

## 已知局限

- 单公司、单币种，未处理期权、或有对价、少数股东权益等复杂科目
- 永续增长法对 `WACC - g` 高度敏感，差距过小时结果不稳定
- 假设反推仅使用最近 3 年平均，未做行业对标与可比公司调整
- 演示数据为虚构，不可用于真实估值结论
