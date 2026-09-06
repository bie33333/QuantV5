A股，这套打板策略怎么样

好的，以下是两份文档：

---

# 📄 文档一：连板股量化因子模型 —— 可读使用说明（面向人类）

## 1. 模型定位
本模型用于**在连续涨停（连板）行情中，筛选具备延续潜力的标的，并规避高位接盘风险**。所有因子均基于**T-1日收盘后已知数据**计算，不含任何未来函数，适用于实盘盘前选股或回测验证。

## 2. 核心逻辑
连板股的本质是“题材 + 小市值 + 游资接力”的短期博弈。模型通过 **8大类因子** 综合评分，从市值、估值、行业、资金、量价等多维度刻画标的的连板健康度，最终输出买入信号（评分≥70且连板高度＜5板）。

## 3. 因子体系一览
| 类别       | 因子                 | 健康/加分条件                                                | 风险/扣分条件                          |
| ---------- | -------------------- | ------------------------------------------------------------ | -------------------------------------- |
| 市值       | 总市值               | ＜100亿（加分），20-50亿（额外加分）                         | ＞500亿（弱信号）                      |
| 估值       | 市盈率（TTM）        | 亏损（PE<0）或 PE>100（极端估值加分）                        | PE在20-100之间（中庸，不加分）         |
| 行业       | 申万一级行业         | 前8大热点行业（机械、医药、化工、计算机、电子、电力设备、汽车、有色） | 其他行业                               |
| 资金       | 昨日龙虎榜           | 游资净买入 且 机构净卖出（最强信号）                         | 游资净卖出或机构净买入                 |
| 动量       | 当前连板高度         | 1-3板（低位加分）                                            | ≥5板（高位扣分）                       |
| 情绪       | 昨日涨停晋级率       | ＞30%（情绪高潮加分）                                        | ＜15%（冰点减仓）                      |
| 量能       | 自由换手率           | 15%~45%（健康换手）                                          | ＜10%（缩量难接力）或＞60%（爆量出货） |
| 量比       | 相对20日均量         | 1.5~3.0（温和放量）                                          | ＞5.0（异常爆量）                      |
| 封板质量   | 封单额/成交额        | ＞10%（高质量封板）                                          | ＜3%（弱封板）                         |
| 竞价承接   | 竞价量/昨日量*换手   | 0.5~2.0（承接适中）                                          | ＞3.0（过度透支）                      |
| 一字板占比 | 历史连板中一字板比例 | ＜0.7（有换手机会）                                          | =1.0（纯一字，无参与机会）             |
| 波动率     | 过去20日收盘价波动率 | ＞3%（适合短线弹性）                                         | ＜1.5%（爆发力弱）                     |

## 4. 评分与信号
- **满分100分**，由上述因子的加分项累加，扣分项直接减去。
- **买入信号**：总分 ≥ 70 且 当前连板数 < 5。
- **卖出/回避**：总分 < 50 或 连板数 ≥ 5 且出现爆量（换手＞60%）或一字板占比=100%。

## 5. 回测标签（仅用于验证，不作为信号）
- **T+5超额胜率**：历史上该信号发出后，5日内跑赢沪深300的概率约46.99%（可作为基准参考）。
- **T+60涨跌幅**：历史中位数为-6.58%，提示中期持有风险。

## 6. 使用建议
- 每日盘前（9:15前）计算所有涨停股的上述因子，筛选出信号标的。
- 开盘后观察竞价和分时承接，结合市场情绪再作最终决策。
- 严格止损，建议以-5%~-8%作为止损线。

---

# 📄 文档二：连板股量化因子模型 —— Agent技术文档（机器可解析）

## 1. 元信息
```json
{
  "model_name": "LimitUp_Factor_Model_v1.0",
  "description": "无未来函数连板股选股模型，基于T-1日数据生成信号",
  "signal_generation_time": "T日盘前（开盘前）",
  "target_label": "T+5超额收益（仅回测）",
  "version": "1.0"
}
```

## 2. 因子定义（JSON Schema）
```json
{
  "factors": [
    {
      "id": "MV",
      "name": "总市值",
      "category": "市值",
      "formula": "MV = CLOSE_T-1 * TOTAL_SHARES",
      "data_source": "交易所日终",
      "scoring": [
        {"condition": "MV < 100e8", "weight": 25, "type": "add"},
        {"condition": "20e8 <= MV < 50e8", "weight": 10, "type": "add"}
      ]
    },
    {
      "id": "PE",
      "name": "市盈率TTM",
      "category": "估值",
      "formula": "IF NET_PROFIT_TTM <= 0 THEN PE = -1 ELSE PE = MV / NET_PROFIT_TTM",
      "data_source": "最新财报",
      "scoring": [
        {"condition": "PE < 0 OR PE > 100", "weight": 20, "type": "add"}
      ]
    },
    {
      "id": "INDUSTRY",
      "name": "热点行业",
      "category": "行业",
      "formula": "INDUSTRY_1 ∈ ['机械设备','医药生物','基础化工','计算机','电子','电力设备','汽车','有色金属']",
      "data_source": "申万分类",
      "scoring": [
        {"condition": "true", "weight": 20, "type": "add"}
      ]
    },
    {
      "id": "NET_BROKER",
      "name": "游资净买入",
      "category": "资金",
      "formula": "NET_BROKER = BUY_AMT_T-1(BROKER) - SELL_AMT_T-1(BROKER)",
      "data_source": "龙虎榜T-1",
      "scoring": [
        {"condition": "NET_BROKER > 0", "weight": 10, "type": "add"}
      ]
    },
    {
      "id": "NET_INST",
      "name": "机构净卖出",
      "category": "资金",
      "formula": "NET_INST = BUY_AMT_T-1(INST) - SELL_AMT_T-1(INST)",
      "data_source": "龙虎榜T-1",
      "scoring": [
        {"condition": "NET_INST < 0", "weight": 10, "type": "add"}
      ]
    },
    {
      "id": "BOARD_COUNT",
      "name": "当前连板数",
      "category": "动量",
      "formula": "连续涨停天数截至T-1",
      "data_source": "行情",
      "scoring": [
        {"condition": "BOARD_COUNT <= 3", "weight": 0, "type": "noop"},
        {"condition": "BOARD_COUNT >= 5", "weight": -20, "type": "add"}
      ]
    },
    {
      "id": "PREV_WIN_RATE",
      "name": "昨日涨停晋级率",
      "category": "情绪",
      "formula": "PREV_WIN_RATE = (T-1日连板股数 / T-1日涨停股数)",
      "data_source": "全市场行情",
      "scoring": [
        {"condition": "PREV_WIN_RATE > 0.30", "weight": 10, "type": "add"},
        {"condition": "PREV_WIN_RATE < 0.15", "weight": -10, "type": "add"}
      ]
    },
    {
      "id": "TURNOVER_FREE",
      "name": "自由换手率",
      "category": "量能",
      "formula": "TURNOVER_FREE = VOLUME_T-1 / FREE_FLOAT_SHARES",
      "data_source": "行情+股东结构",
      "scoring": [
        {"condition": "0.15 <= TURNOVER_FREE <= 0.45", "weight": 15, "type": "add"},
        {"condition": "TURNOVER_FREE > 0.60", "weight": -15, "type": "add"}
      ]
    },
    {
      "id": "VOL_RATIO",
      "name": "量比（相对20日均量）",
      "category": "量能",
      "formula": "VOL_RATIO = VOLUME_T-1 / MA(VOLUME, 20)_T-2",
      "data_source": "行情",
      "scoring": [
        {"condition": "1.5 <= VOL_RATIO <= 3.0", "weight": 10, "type": "add"},
        {"condition": "VOL_RATIO > 5.0", "weight": -10, "type": "add"}
      ]
    },
    {
      "id": "SEAL_RATIO",
      "name": "封板质量",
      "category": "量价形态",
      "formula": "SEAL_RATIO = SEAL_AMOUNT_T-1 / AMOUNT_T-1",
      "data_source": "逐笔/涨停数据",
      "scoring": [
        {"condition": "SEAL_RATIO > 0.10", "weight": 10, "type": "add"}
      ]
    },
    {
      "id": "AUCTION_STRENGTH",
      "name": "竞价承接强度",
      "category": "量价形态",
      "formula": "AUCTION_STRENGTH = (AUCTION_VOL_T / VOLUME_T-1) * TURNOVER_FREE",
      "data_source": "集合竞价数据（T日开盘前获取，但可用T-1预测？实际需实盘获取，回测可用T日开盘数据，但注意未来。**修正**：此处改用T-1日竞价数据？通常竞价数据在T-1日没有。建议改为“昨日竞价成交比”或“开盘前可用”。为严格无未来，我们将此因子改为基于T-1日盘中的“封单撤单比”或“盘中开板次数”。但用户已接受之前的表述，实际上竞价强度需要T日开盘前数据，但若在盘前计算，T日竞价数据其实已产生（在9:25），并非未来，属于盘中实时。为严格，我们在技术文档中注明数据获取时间点为T日9:25后。但为了统一，我们可改为“开盘前可用”，不算未来。我们保持原样，但注明。",
      "scoring": [
        {"condition": "0.5 <= AUCTION_STRENGTH <= 2.0", "weight": 5, "type": "add"}
      ]
    },
    {
      "id": "ONE_WORD_RATIO",
      "name": "一字板占比",
      "category": "量价形态",
      "formula": "ONE_WORD_RATIO = ONE_WORD_COUNT / BOARD_COUNT_T-1  （若BOARD_COUNT=0则忽略）",
      "data_source": "历史涨停类型",
      "scoring": [
        {"condition": "ONE_WORD_RATIO < 0.7", "weight": 0, "type": "noop"},
        {"condition": "ONE_WORD_RATIO == 1.0", "weight": -15, "type": "add"}
      ]
    },
    {
      "id": "VOLATILITY",
      "name": "过去20日波动率",
      "category": "动量",
      "formula": "VOLATILITY = STD(CLOSE_i / CLOSE_i-1 - 1, 20) for i = T-20..T-1",
      "data_source": "行情",
      "scoring": [
        {"condition": "VOLATILITY > 0.03", "weight": 0, "type": "noop"},
        {"condition": "VOLATILITY < 0.015", "weight": -5, "type": "add"}
      ]
    }
  ]
}
```

## 3. 信号生成逻辑（Python伪代码）
```python
def generate_signal(stock_data_Tminus1, market_data_Tminus1):
    score = 0
    for factor in factors:
        value = compute(factor['formula'], stock_data_Tminus1, market_data_Tminus1)
        for rule in factor['scoring']:
            if eval(rule['condition']):  # 实际用条件判断
                score += rule['weight']
    # 额外条件：连板高度限制
    board_count = stock_data_Tminus1['board_count']
    if board_count >= 5:
        score -= 20  # 已在因子中处理，但可再强调
    # 最终信号
    if score >= 70 and board_count < 5:
        return {"signal": 1, "score": score}
    else:
        return {"signal": 0, "score": score}
```

## 4. 回测标签（仅用于验证）
```json
{
  "label_T5_excess_win": "Excess_Ret_T5 = (CLOSE_T+5/CLOSE_T -1) - (HS300_T+5/HS300_T -1) > 0",
  "label_T60_return": "Ret_T60 = CLOSE_T+60/CLOSE_T -1",
  "historical_benchmark": {
    "T5_win_rate": 0.4699,
    "T60_median_return": -0.0658
  }
}
```

## 5. 数据依赖清单
- 日线行情：开盘、收盘、最高、最低、成交量、成交额
- 股本数据：总股本、流通股本、持股>5%大股东名单（用于自由流通股本）
- 龙虎榜数据（T-1日）：营业部买卖金额、机构买卖金额
- 涨停数据：连续涨停天数、是否一字板、封单金额
- 集合竞价数据（T日盘前）：开盘前竞价成交量（可用于实时决策，但若回测需注意可用性，可降级使用T-1日尾盘封单变化替代）

## 6. 注意事项
- 所有计算均基于T-1日收盘后已知数据，但**竞价承接强度**涉及T日开盘竞价数据，需在T日9:25后获取，若回测中需避免未来，可使用T-1日盘后“封单撤单比”或“尾盘封单变化率”作为替代。本技术文档保留该因子但注明实时性。
- 建议回测时采用滑动窗口，每日滚动计算。

---

以上两份文档可供人类阅读理解和Agent程序直接解析。如需进一步调整，请告知。



这套策略**有一定逻辑，但按现在的版本，我不会直接拿去实盘打板**。

核心问题不是“因子太少”，而是**因子方向、评分体系和交易时点存在几个比较严重的问题**。尤其是你给出的历史结果——**T+5 超额胜率 46.99%、T+60 中位数 -6.58%**——实际上已经在提醒你：目前这套模型更像“连板股画像”，还不是一个成熟的“买入策略”。

我可以进一步把它改造成真正适合 A 股短线的版本。

### 我先给你一个总体评价

| 模块          | 当前评价 | 问题                           |
| ------------- | -------- | ------------------------------ |
| 小市值        | ⭐⭐⭐⭐     | 有效，但不能简单理解为越小越好 |
| 连板高度      | ⭐⭐⭐⭐     | 控制高位风险是正确的           |
| 换手率        | ⭐⭐⭐⭐     | 是比较重要的接力因子           |
| 量能          | ⭐⭐⭐      | 有用，但固定阈值容易失效       |
| 龙虎榜        | ⭐⭐       | 当前定义过于粗糙               |
| PE            | ⭐        | **建议删除或大幅降权**         |
| 热点行业      | ⭐⭐       | 太静态                         |
| 封单额/成交额 | ⭐⭐⭐      | 有价值，但容易被“假封单”误导   |
| 竞价承接      | ⭐⭐⭐⭐⭐    | **非常重要，但现在定义有问题** |
| 一字板占比    | ⭐⭐⭐      | 有一定意义                     |
| 波动率        | ⭐⭐       | 对打板策略不是核心变量         |
| 整体评分      | ⭐⭐       | **需要重新设计**               |

**如果满分 10 分，我目前给这套策略约 5.5～6 分。**

但它的框架是可以救的。

------

# 一、最大的硬伤：你的“PE 极端值加分”逻辑不合理

你现在：

> PE < 0 或 PE > 100 → +20

这是我最想删掉的一项。

因为对于 A 股连板股：

**“亏损”并不会天然增加次日涨停概率。**

甚至恰恰相反。

例如：

> A 公司
> 市值 30 亿
> PE = -50
> 连续 3 板

你的模型：

**因为亏损 +20。**

但这并不能说明它更容易 4 板。

你实际上把：

> **基本面差**

错误地当成了：

> **短线强势**

两者完全不是一个东西。

------

# 二、第二个问题：你把“热点行业”做成了静态名单

现在是：

> 机械、医药、化工、计算机、电子、电力设备、汽车、有色

这实际上不是“热点行业”。

这是：

> **历史上经常活跃的行业。**

真正的短线热点是动态的。

比如某一周：

AI → 光模块 → PCB → 机器人

下一周：

低空经济 → 军工 → 卫星

再下一周：

有色 → 黄金 → 稀土

所以：

```text
INDUSTRY ∈ 固定8个行业
```

这个因子的信息量其实很有限。

更好的做法应该是：

### “板块强度”

例如：

```text
板块涨停数量
板块3日涨幅
板块5日涨幅
板块成交额增长
板块内部连板数量
板块最高板高度
板块涨停家数 / 全市场涨停家数
```

然后构造：

```text
THEME_STRENGTH
```

这比“是不是电子行业”有意义得多。

------

# 三、真正的问题：你现在不是在选“龙头”

这是整个策略最关键的问题。

你现在的思路是：

> 市值小
> 换手好
> 量能好
> 龙虎榜好
> 行业热门
> 连板低

于是筛出来：

> 一堆“看起来很健康的连板股”。

但是：

**打板最重要的不是“健康”，而是“谁是市场共识”。**

比如一个板块有：

```text
A：5板
B：3板
C：3板
D：2板
E：1板
```

你的模型可能认为：

> B、C 都不错。

但实际交易中：

**A 才是绝对核心。**

而且：

> B/C 的价值，很大程度上取决于 A 是否继续晋级。

所以你需要加入：

# 龙头/梯队因子

例如：

```text
板块最高板 = 5

当前股票 = 3板

距离板块最高板 = 2
```

以及：

```text
是否为板块最高连板
是否为板块第二高度
是否为同题材唯一3板
同题材涨停数量
同题材晋级率
```

这会明显比 PE 有意义。

------

# 四、你的“龙虎榜”因子也需要重做

你现在：

> 游资净买入 +10
> 机构净卖出 +10

这个逻辑有一个问题：

**你把“机构卖出”直接定义成利好。**

这太粗糙。

比如：

```text
机构卖出 5000万
游资买入 3000万
```

你给：

> +20

但实际上可能是：

**机构砸盘 + 游资接盘失败。**

所以龙虎榜应该研究的是：

### 谁在买

而不是简单：

> 游资买 / 机构卖。

最好进一步拆：

```text
买一金额 / 成交额
买一+买二集中度
知名活跃营业部
机构净买入
机构净卖出
龙虎榜净买入金额
龙虎榜净买入 / 成交额
```

尤其是：

> **买一占比**

对于接力非常重要。

------

# 五、你现在最大的遗漏：市场情绪周期

你虽然有：

> 昨日涨停晋级率

但这远远不够。

打板策略实际上应该先回答：

> **今天是不是适合打板？**

而不是：

> 哪只股票最符合条件？

这是两个完全不同的问题。

------

# 六、建议把策略改成“两层模型”

我非常建议你这么设计：

```text
第一层：
市场环境判断

        ↓

第二层：
个股打板评分
```

------

# 第一层：市场环境

例如每天计算：

### 情绪指标

```text
涨停数量
跌停数量
连板数量
最高板
昨日涨停今日平均收益
昨日连板今日平均收益
涨停晋级率
炸板率
连板晋级率
```

进一步构造：

```text
MARKET_SENTIMENT
```

例如：

| 情绪   | 操作         |
| ------ | ------------ |
| ≥80    | 激进         |
| 60～80 | 正常         |
| 40～60 | 谨慎         |
| 20～40 | 轻仓         |
| <20    | **禁止打板** |

这个“禁止交易”非常重要。

------

# 七、第二层才是个股评分

我建议你把现在的 100 分重新设计。

例如：

## ① 市场地位：25分

```text
板块最高板       +15
板块第二高度     +10
板块唯一高度     +10
同题材涨停数量   +5
```

------

## ② 连板结构：15分

```text
2板      +15
3板      +12
4板      +5
5板以上  -10
```

注意：

**不是连板越低越好。**

1板、2板、3板的交易逻辑完全不同。

------

# 八、换手：15分

你的这个思路可以保留。

但是不要固定：

> 15%～45%

因为不同股票的流动性不同。

更好的方式是：

### 相对换手率

例如：

```text
今日换手 / 过去20日平均换手
```

或者：

```text
当前换手 / 同市值股票换手中位数
```

这样模型更稳定。

------

# 九、量能：10分

你现在：

> 1.5～3倍 +10

思路没问题。

但我会加入：

```text
成交额增长率
量价关系
换手率变化
```

因为：

> 放量 ≠ 好。

真正需要的是：

> **价格上涨 + 成交量合理放大 + 换手充分**

------

# 十、封板质量：10分

这个因子可以保留。

但：

> 封单额 / 成交额

其实不是特别稳定。

最好增加：

```text
封板时间
炸板次数
最后一次回封时间
封单变化
开板持续时间
```

例如：

### 10:00 前封板

和

### 14:55 偷偷封板

虽然最终都是：

> 涨停

但意义完全不同。

------

# 十一、我反而建议加入一个你现在完全没有的因子

# “涨停时间”

这个东西对于打板很有价值。

例如：

```text
09:30～09:35     强
09:35～10:00     较强
10:00～11:00     中性
11:00～13:30     偏弱
13:30～14:30     弱
14:30～14:57     极弱
```

当然不能机械使用。

但作为：

> **封板质量因子**

非常有意义。

------

# 十二、还应该加入“炸板率”

例如：

```text
过去20个交易日：

涨停 → 炸板 → 回封
```

统计：

```text
炸板次数
炸板率
平均炸板时间
回封成功率
```

因为：

**一只股票今天封得死不死，和它过去的封板稳定性有关。**

------

# 十三、还有一个非常重要：次日溢价

这是我认为你这套模型最缺的东西。

你真正想预测的是：

> **今天打板，明天有没有溢价？**

那么应该直接计算：

```text
股票过去N次涨停后的：

次日开盘收益
次日最高收益
次日收盘收益
次日涨停概率
```

例如：

```text
过去10次涨停：

次日平均开盘 +3.2%
次日平均最高 +6.8%
次日平均收盘 +1.9%
次日负收益概率 20%
```

那么这个股票：

**“打板后的次日溢价”历史上非常好。**

这个因子的实际意义可能比：

> PE

高几个数量级。

------

# 十四、你现在的止损也需要重新考虑

你写：

> -5%～-8%

我认为对于打板策略：

**固定 -5%～-8% 止损不够科学。**

因为：

### A

炸板：

-3%

但承接非常强。

可能第二天反包。

而：

### B

低开 -2%

然后一路：

-2 → -4 → -6 → -8

实际上已经完全走坏。

所以应该加入：

> **结构止损**

例如：

```text
跌破昨日涨停价
+
跌破关键分时承接
+
板块龙头走弱
```

作为退出条件。

------

# 十五、最重要的是：重新定义你的回测目标

你现在：

> T+5 超额收益

我觉得这个目标**不适合评价打板策略**。

因为打板是极短线。

你应该重点看：

### T+1

```text
次日开盘收益
次日最高收益
次日收盘收益
```

### T+2

```text
T+2最高收益
T+2收盘收益
```

### 交易层面

```text
胜率
平均盈利
平均亏损
盈亏比
最大回撤
连续亏损次数
Profit Factor
年化收益
```

最重要的是：

# 实际策略收益

而不是：

> T+5 有没有跑赢沪深300。

因为你不是在做：

> 中短线 alpha。

你是在做：

> **A股涨停接力。**

------

# 十六、还有一个非常危险的问题：你的回测可能存在“交易不可实现”

这是我建议你下一步重点检查的。

比如模型说：

> T日买入。

但是：

### 如果股票 T 日直接一字涨停

你根本买不到。

如果回测按照：

> T日收盘价买入

那就会产生严重的：

**虚假成交。**

所以必须模拟：

```text
涨停价挂单
↓
是否有成交机会
↓
封单排队
↓
成交量
↓
实际成交概率
```

否则回测收益可能非常漂亮，但实盘完全不能复制。

------

# 十七、我会把你的模型改成这个结构

最终可以变成：

```text
                 市场情绪
                    │
                    ↓
             是否允许打板？
                    │
             ┌──────┴──────┐
             │             │
           NO              YES
             │             │
          不交易            ↓
                       板块强度
                           │
                           ↓
                      市场地位
                           │
                           ↓
                      连板结构
                           │
                           ↓
                    换手/量价结构
                           │
                           ↓
                     封板质量
                           │
                           ↓
                     龙虎榜结构
                           │
                           ↓
                    次日历史溢价
                           │
                           ↓
                       综合评分
                           │
                           ↓
                     实际交易过滤
                           │
                           ↓
                       买入/放弃
```

这就比现在：

> 市值 + PE + 行业 + 龙虎榜 + 换手 + 量比

高级一个层级。

------

# 十八、如果让我直接修改你的评分，我会这样做

### **100分版本**

| 因子          | 权重   |
| ------------- | ------ |
| 市场情绪      | **15** |
| 板块强度      | **15** |
| 龙头/市场地位 | **20** |
| 连板结构      | **10** |
| 换手结构      | **10** |
| 量价关系      | **8**  |
| 封板质量      | **8**  |
| 龙虎榜        | **5**  |
| 次日历史溢价  | **7**  |
| 市值          | **2**  |
| PE            | **0**  |

我会直接：

**PE 删除。**

行业固定名单删除。

波动率降到很低甚至删除。

然后把权重给：

> **市场情绪 + 板块强度 + 龙头地位 + 次日溢价**

这四个才是我认为真正应该成为核心的东西。

------

## 最后一个关键判断

你现在这个模型最大的优点是：

> **已经开始从“凭感觉打板”向“可量化交易”转变。**

但是它现在还是：

> **“因子选股模型”**

而不是：

> **“完整打板交易系统”。**

真正成熟的版本应该同时解决：

**① 今天能不能打板
② 哪个板块值得做
③ 板块里面谁最强
④ 这个票什么时候买
⑤ 买不到怎么办
⑥ 炸板怎么办
⑦ 第二天什么时候卖
⑧ 连续亏损怎么办
⑨ 一字板如何处理
⑩ 实际排板能不能成交**

尤其是**“买不到/成交概率”**，是很多A股打板回测最容易造假的地方。

如果你愿意，我下一步可以直接把你这套 **LimitUp_Factor_Model_v1.0 重构成一个 v2.0**：给你完整的 **因子公式 + 100分评分表 + 市场情绪周期 + 龙头识别 + 买入规则 + 卖出规则 + 仓位管理 + 严格无未来函数回测规则**，最后可以直接交给 Python/量化 Agent 实现。



是的，按照你说的帮我重构。



可以。下面我直接把它重构成一套 **LimitUp_Factor_Model v2.0**。

先说明一个很重要的变化：**我不会继续把它设计成“找高分股票”这么简单，而是设计成“市场环境 → 板块 → 个股 → 买点 → 成交 → 卖出”的完整打板系统。**

另外，当前是 2026 年，交易制度已经发生变化。例如上交所 2026 年修订规则已于 2026 年 7 月 6 日实施，主板风险警示股票的涨跌幅限制也调整为 10%；科创板仍为 20%。深交所主板为 10%、创业板为 20%。因此回测引擎必须按股票实际板块、风险状态动态计算涨停价，不能简单写死“10%涨停”。([上海电力股份有限公司](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml?utm_source=chatgpt.com))

------

# 一、LimitUp_Factor_Model v2.0

## 1. 模型定位

> **A股短线连板/涨停接力量化交易模型**

目标不是预测：

> “这只股票未来一个月涨多少？”

而是预测：

> **“在当前市场环境下，这只股票今天是否值得参与涨停接力，以及买入后 T+1 是否具有正向风险收益比。”**

核心预测周期：

- T+0：买入
- T+1：主要卖出窗口
- T+2：次要观察窗口
- T+5：仅作为辅助统计
- T+60：取消作为核心评价指标

------

# 二、整个系统改成五层

```text
                 ┌──────────────┐
                 │  ①市场情绪层  │
                 └──────┬───────┘
                        ↓
                 是否允许打板？
                        ↓
                 ┌──────────────┐
                 │  ②板块强度层  │
                 └──────┬───────┘
                        ↓
                 哪个题材最值得做？
                        ↓
                 ┌──────────────┐
                 │  ③个股强度层  │
                 └──────┬───────┘
                        ↓
                 谁是板块核心？
                        ↓
                 ┌──────────────┐
                 │  ④买入执行层  │
                 └──────┬───────┘
                        ↓
                 今天什么价格买？
                        ↓
                 ┌──────────────┐
                 │  ⑤退出管理层  │
                 └──────────────┘
                        ↓
                 T+1/T+2怎么卖？
```

这五层必须分开。

------

# 三、第一层：市场情绪模型

这是 v2.0 最大的变化。

以前：

> 找到高分股 → 买。

现在：

> **先判断今天有没有资格打板。**

------

## MARKET_SENTIMENT

建立一个 100 分的市场情绪指数。

| 因子                    | 权重 |
| ----------------------- | ---- |
| 涨停数量                | 15   |
| 跌停数量                | 10   |
| 涨停晋级率              | 15   |
| 昨日涨停股 T+1 平均收益 | 15   |
| 昨日连板股 T+1 平均收益 | 15   |
| 炸板率                  | 10   |
| 最高连板高度            | 10   |
| 连板家数                | 10   |

得到：

```text
MARKET_SENTIMENT ∈ [0,100]
```

------

## 情绪状态

```text
80-100    极强
65-80     强势
50-65     正常
35-50     弱势
20-35     冰点
0-20      极弱
```

然后直接产生一个：

```text
TRADE_PERMISSION
```

### 交易权限：

| 情绪  | 操作                 |
| ----- | -------------------- |
| ≥80   | 正常打板             |
| 65-80 | 正常参与             |
| 50-65 | 精选                 |
| 35-50 | 轻仓                 |
| <35   | **禁止新增打板仓位** |

这一步非常重要。

因为：

> **一个 90 分的股票，在 25 分情绪周期里，依然可能不值得买。**

------

# 四、第二层：板块强度模型

彻底删除原来的：

> “机械/医药/化工/计算机……”

这种固定热点名单。

改成：

# THEME_STRENGTH

动态计算每个题材/行业。

------

## 板块评分

| 因子                 | 权重 |
| -------------------- | ---- |
| 当日板块涨停数量     | 20   |
| 板块 3 日收益        | 15   |
| 板块 5 日收益        | 10   |
| 板块成交额增长       | 15   |
| 板块涨停占全市场比例 | 10   |
| 板块连板数量         | 10   |
| 板块最高板高度       | 10   |
| 板块内部晋级率       | 10   |

得到：

```text
THEME_SCORE = 0~100
```

------

# 五、增加“板块持续性”

这是非常关键的一项。

因为：

> 今天突然涨停 10 家

不一定是好板块。

可能只是：

> 一日游。

所以增加：

```text
THEME_PERSISTENCE
```

计算：

```text
过去5日：
板块涨停数量
板块成交额
板块涨幅
板块连板数量
```

如果：

```text
T-4 ↑
T-3 ↑
T-2 ↑
T-1 ↑
T ↑
```

那么：

**持续性强。**

如果：

```text
T-1突然暴涨
T当天回落
```

则：

**持续性弱。**

------

# 六、第三层：个股评分

现在才进入股票。

总分：

# STOCK_SCORE = 100

我建议重新分配：

| 因子         | 权重    |
| ------------ | ------- |
| 市场地位     | **20**  |
| 板块强度     | **15**  |
| 连板结构     | **10**  |
| 换手结构     | **10**  |
| 量价关系     | **8**   |
| 封板质量     | **8**   |
| 次日历史溢价 | **7**   |
| 龙虎榜结构   | **5**   |
| 市值         | **2**   |
| 竞价强度     | **15**  |
| **合计**     | **100** |

注意：

**竞价强度只有在 T 日 9:25 后才能使用。**

所以这个模型实际上应该有两个版本：

```text
T-1 盘后模型
T  日 9:25 模型
```

不能把 9:25 数据伪装成 T-1 数据。

------

# 七、核心因子①：市场地位

这是我认为整个模型最重要的因子。

## LEADERSHIP_SCORE

### 板块最高板

```text
+20
```

### 与最高板差 1 板

```text
+15
```

### 与最高板差 2 板

```text
+8
```

### 普通跟风

```text
0~5
```

进一步增加：

### “唯一高度”

例如：

```text
机器人：

A 4板
B 3板
C 2板
D 2板
```

A：

> 唯一4板。

这是极强信号。

------

# 八、核心因子②：连板结构

我不会简单规定：

> 1～3板加分，5板扣分。

重新设计：

| 连板 | 基础分 |
| ---- | ------ |
| 首板 | 4      |
| 2板  | 10     |
| 3板  | 10     |
| 4板  | 8      |
| 5板  | 5      |
| ≥6板 | 0      |

但还有一个非常重要的东西：

> **连板高度必须结合市场最高板。**

例如：

### 市场最高板 = 3

你的股票 = 3板

这是：

> 市场核心。

但是：

### 市场最高板 = 8

你的股票 = 3板

这时候：

> 只是低位跟风。

所以：

```text
RELATIVE_HEIGHT
```

必须存在。

------

# 九、核心因子③：换手

保留你原来的思路，但改成：

# RELATIVE_TURNOVER

不要固定：

> 15%～45%。

而是：

```text
今日换手率
/
过去20日该股票平均换手率
```

例如：

```text
当前换手 = 20%

历史平均 = 8%

Relative = 2.5
```

说明：

> 市场参与度显著提高。

------

# 十、换手结构评分

```text
0.8～1.2    低
1.2～2.0    良好
2.0～3.5    强
3.5～5.0    过热
>5          极端
```

但这里有一个重要例外：

**2板/3板允许更高换手。**

因为：

> 连板接力本身就是资金换手。

所以需要：

```text
BOARD_COUNT
+
RELATIVE_TURNOVER
```

联合评分。

------

# 十一、核心因子④：量价关系

原来的：

> VOL_RATIO 1.5～3

可以保留，但升级。

加入：

```text
VOLUME_EXPANSION
PRICE_RETURN
TURNOVER_CHANGE
```

核心判断：

### 好

```text
价格上涨
+
成交量温和增加
+
换手增加
```

### 差

```text
价格上涨
+
成交量突然5倍
+
换手极端
```

因为这可能是：

> 情绪高潮/资金兑现。

------

# 十二、核心因子⑤：封板质量

建立：

# BOARD_QUALITY

由：

```text
封板时间
炸板次数
开板总时长
最终封板时间
封单金额
封单变化
```

构成。

------

## 封板时间评分

比如：

```text
09:30-09:35    10
09:35-10:00     8
10:00-11:00     6
11:00-13:30     4
13:30-14:30     2
14:30以后       0
```

但这里不能机械理解为：

> 越早越好。

因为：

**一字板 ≠ 高质量换手板。**

所以还要结合：

```text
ONE_WORD
TURNOVER
```

------

# 十三、炸板因子

增加：

# BREAK_BOARD_SCORE

例如：

```text
当天炸板次数 = 0
+10

炸板1次
+7

炸板2次
+4

炸板≥3
0
```

再加入：

> 回封速度。

例如：

```text
炸板 → 2分钟回封

比

炸板 → 40分钟回封

强得多。
```

------

# 十四、最重要的新因子：历史次日溢价

这个我强烈建议加入。

叫：

# NEXT_DAY_PREMIUM

统计该股票历史上：

> 涨停之后第二天表现。

例如过去20次涨停：

```text
T+1开盘平均：+2.8%

T+1最高平均：+6.1%

T+1收盘平均：+1.4%

T+1负收益率：25%
```

可以转成：

```text
NEXT_DAY_PREMIUM_SCORE
```

0～7分。

这才真正贴近：

> 打板策略的目标函数。

------

# 十五、龙虎榜重新设计

不再使用：

> 游资买入 +10
> 机构卖出 +10

改成：

# MONEY_FLOW_SCORE

考虑：

```text
龙虎榜净买入 / 成交额
```

以及：

```text
买一占比
买一+买二集中度
机构净买入比例
活跃营业部历史表现
```

例如：

```text
龙虎榜净买入/成交额 > 5%
+3

买一集中度合理
+2
```

机构买卖不再机械判断。

------

# 十六、市值降到2分

市值仍然保留。

但只作为：

> **辅助因子。**

例如：

```text
20～50亿     +2
50～100亿    +1
100～200亿    0
>200亿       -1
```

因为：

> 小市值只是“容易被炒作”的条件之一。

绝对不能成为买入理由。

------

# 十七、PE：直接删除

我建议 v2.0：

```text
PE_SCORE = 0
```

甚至从数据库里保留，但：

> 不参与模型评分。

原因很简单：

**我们不是在做价值投资模型。**

------

# 十八、竞价模型

这是 T 日最重要的最后一道过滤器。

9:25 后重新计算：

# AUCTION_SCORE

包含：

```text
竞价涨幅
竞价成交额
竞价成交量
竞价换手
竞价金额 / 昨日成交额
竞价价格稳定性
```

------

## 例如：

### 极强

```text
竞价 +5%
+
竞价成交额充足
+
价格稳定
+
没有大幅撤单
```

### 危险

```text
竞价 +9%
+
成交量异常巨大
+
接近涨停开盘
+
板块整体走弱
```

后者反而可能是：

> 高开兑现。

------

# 十九、必须增加一个“禁止交易过滤器”

即：

# HARD_FILTER

哪怕股票 100 分，只要满足下面任何一个：

```text
市场情绪 < 35
```

或者：

```text
板块强度 < 50
```

或者：

```text
连续多个交易日高位爆量
```

或者：

```text
当日重大监管风险
```

或者：

```text
一字板无法成交
```

或者：

```text
流动性不足
```

则：

# 不交易。

这比把分数从 90 降到 70 更合理。

------

# 二十、最终买入信号

我建议：

```text
if MARKET_SENTIMENT < 35:
    NO_TRADE

elif THEME_SCORE < 50:
    NO_TRADE

elif STOCK_SCORE < 75:
    NO_TRADE

elif LEADERSHIP_SCORE < threshold:
    NO_TRADE

elif AUCTION_SCORE < threshold:
    NO_TRADE

else:
    TRADE
```

注意：

**75不是神奇数字。**

最终必须通过 walk-forward 回测寻找最优阈值。

------

# 二十一、把买入分成三种

不要只有：

> 买 / 不买。

增加：

### A级

```text
Score ≥ 85
市场情绪 ≥65
板块 ≥70
市场地位强
```

→ 正常仓位

### B级

```text
75～85
```

→ 半仓

### C级

```text
70～75
```

→ 观察，不主动打板

------

# 二十二、仓位管理

我不建议：

> 每次固定满仓。

设计成：

```text
市场情绪 ≥80
A级：20%～30%

65～80
A级：15%～20%

50～65
A级：10%

<50
禁止新增
```

同时：

**单票最大仓位 30%。**

这样即使模型出现连续错误，也不会一次性造成严重损失。

------

# 二十三、真正的买入逻辑

这也是 v2.0 和普通回测最大的区别。

不是：

> “涨停了 → 假设买入。”

而是：

```text
候选股
 ↓
涨停
 ↓
是否有实际成交机会？
 ↓
有
 ↓
是否属于主动封板？
 ↓
是
 ↓
板块是否同步？
 ↓
是
 ↓
买入
```

------

# 二十四、必须模拟“买不到”

这是整个回测系统最重要的部分之一。

如果：

```text
涨停价 = 10.00

封单 = 8亿元

当日涨停成交量 = 1000万元
```

你不能在回测里直接说：

> 10元买入。

因为真实情况是：

**你可能排不到。**

因此建立：

# EXECUTION_PROBABILITY

估算：

```text
成交量
/
封单量
```

再考虑：

```text
你的排队时间
订单提交时间
封单变化
```

最终模拟：

```text
成交
/
部分成交
/
无法成交
```

------

# 二十五、卖出策略

我建议彻底放弃：

> 固定 -5%～-8% 止损。

采用：

# T+1退出系统

------

## 情况① 高开

例如：

```text
T+1 高开 +5%
```

观察：

```text
板块是否强
龙头是否强
成交量是否正常
```

如果：

> 高开后快速跌破开盘价

可以退出。

------

# 二十六、情况② 低开

例如：

```text
-3%
```

如果：

```text
板块强
龙头强
个股快速收复昨日收盘价
```

允许继续观察。

如果：

```text
低开
+
持续走弱
+
跌破关键支撑
+
板块退潮
```

直接退出。

------

# 二十七、情况③ 炸板

如果你是涨停价买入：

```text
涨停
↓
炸板
```

不能简单：

> 炸板就卖。

因为：

### 强势回封

```text
炸板
↓
快速回封
```

可能是健康换手。

而：

### 弱势炸板

```text
炸板
↓
持续下跌
↓
板块同步走弱
```

应该快速退出。

------

# 二十八、增加“市场退潮熔断”

如果：

```text
MARKET_SENTIMENT
从 70
↓
40
```

或者：

```text
最高板断板
+
涨停晋级率快速下降
+
炸板率快速上升
```

系统自动：

> **禁止新增仓位。**

甚至可以降低已有仓位。

------

# 二十九、回测评价体系

以前：

> T+5 超额胜率 46.99%

这个指标以后只能当辅助指标。

核心改成：

| 指标            | 权重  |
| --------------- | ----- |
| T+1平均收益     | ⭐⭐⭐⭐⭐ |
| T+1胜率         | ⭐⭐⭐⭐⭐ |
| T+1盈亏比       | ⭐⭐⭐⭐⭐ |
| T+1最大亏损     | ⭐⭐⭐⭐  |
| Profit Factor   | ⭐⭐⭐⭐⭐ |
| 最大回撤        | ⭐⭐⭐⭐⭐ |
| 连续亏损次数    | ⭐⭐⭐⭐  |
| T+2收益         | ⭐⭐⭐   |
| T+5收益         | ⭐⭐    |
| 沪深300超额收益 | ⭐     |

------

# 三十、必须做 Walk-forward

不能：

```text
2019-2026全部数据
↓
训练
↓
测试
```

这样容易过拟合。

应该：

```text
2019-2022
训练

2023
测试

↓

2020-2023
训练

2024
测试

↓

2021-2024
训练

2025
测试

↓

2022-2025
训练

2026
测试
```

最后：

> 汇总所有 out-of-sample 结果。

这样才有意义。

------

# 三十一、还必须做市场分周期回测

至少拆：

```text
牛市
震荡市
熊市
情绪高潮
情绪退潮
情绪冰点
```

你最终很可能发现：

> **这套策略不是任何时候都赚钱。**

这并不是坏事。

恰恰说明：

> 市场状态过滤器有效。

------

# 三十二、最终 v2.0 架构

最终数据库大概是：

```text
Market
├── market_sentiment
├── limit_up_count
├── limit_down_count
├── promotion_rate
├── broken_board_rate
├── highest_board
└── yesterday_limitup_return

Theme
├── theme_score
├── theme_persistence
├── theme_limitup_count
├── theme_board_height
├── theme_turnover_growth
└── theme_promotion_rate

Stock
├── board_count
├── relative_height
├── leadership_score
├── turnover_score
├── volume_score
├── board_quality
├── money_flow
├── next_day_premium
├── market_cap
└── auction_score

Execution
├── limit_price
├── queue_size
├── queue_position
├── execution_probability
└── actual_fill

Risk
├── market_regime
├── theme_regime
├── stock_regime
└── position_size
```

------

# 三十三、最重要的改变

如果把你原来的 v1.0 和现在这个 v2.0 放在一起：

### v1.0

```text
市值
+
PE
+
行业
+
龙虎榜
+
换手
+
量比
+
封单
+
竞价
=
分数
```

本质是：

> **“这只股票看起来像不像强势股？”**

------

### v2.0

```text
市场周期
    ↓
板块周期
    ↓
龙头地位
    ↓
个股结构
    ↓
竞价确认
    ↓
成交概率
    ↓
仓位
    ↓
T+1退出
```

变成：

> **“在当前市场环境下，这笔交易有没有正期望？”**

这才是我认为真正值得回测的方向。

------

## 最后，我建议再做一个重要升级

**不要马上开始优化这些权重。**

先把整个系统做成一个**事件驱动回测器**。

因为现在最关键的问题已经不是：

> “20分还是15分？”

而是：

> **如果一个股票在 9:31 封板，我到底能不能买到？如果9:47炸板，13:52回封，我的模型应该怎么处理？第二天9:35应该怎么卖？**

这些问题解决以后，才有资格优化因子。

而且你的回测数据最好至少包含：

**1分钟/5分钟行情 + 涨停状态 + 封单/盘口数据 + 龙虎榜 + 板块分类 + 竞价数据。**

否则仅靠日线数据，很难真实模拟打板。

另外，回测时一定要按实际板块涨跌幅制度处理，不能把所有 A 股统一按 10% 计算；例如当前沪市主板股票一般为10%，科创板为20%，深市主板为10%、创业板为20%。([上海电力股份有限公司](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml?utm_source=chatgpt.com))

**下一步我建议直接进入“v2.0 技术规格书”阶段**：我可以把上面这套东西进一步写成一份**可以直接交给 Python Agent 开发的 JSON Schema + 数据库表结构 + 因子公式 + 回测伪代码 + 买卖撮合规则**，而不是停留在策略讨论层面。



是的，继续吧



可以。下面我把它正式定义成 **LimitUp_Factor_Model v2.0 技术规格书**，目标是做到：**Python Agent 拿到这份文档后，可以直接开始建库、写因子、跑回测，而不是还需要自己猜交易规则。**

先修正上一版一个关键点：**不能把“涨停”简单理解为固定 +10%**。当前深交所 2026 年交易规则明确规定主板股票涨跌幅限制为 10%、创业板为 20%；上交所科创板为 20%，且 2026 年 7 月起上交所主板风险警示股票的涨跌幅限制已调整为 10%。因此系统必须让 `limit_pct` 成为股票级动态字段。([深交所文档](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf?utm_source=chatgpt.com))

------

# LimitUp_Factor_Model v2.0

## 0. 模型最终目标

模型不再预测：

> “这只股票会不会继续上涨？”

而是预测：

> **“在当前市场状态下，这只股票的涨停接力是否具有正期望收益，并且这笔交易是否具有实际成交可能？”**

最终输出：

```json
{
  "signal": "BUY",
  "score": 87.4,
  "market_regime": "STRONG",
  "theme": "机器人",
  "theme_score": 82.1,
  "leadership_score": 19.2,
  "execution_probability": 0.73,
  "position": 0.20,
  "entry_type": "LIMIT_UP_RETEST",
  "risk_level": "MEDIUM"
}
```

------

# 1. 系统总体架构

```text
                    ┌────────────────────┐
                    │   Market Data      │
                    └─────────┬──────────┘
                              ↓
                 ┌─────────────────────────┐
                 │  ① Market Regime Engine │
                 └────────────┬────────────┘
                              ↓
                      是否允许打板？
                              ↓
                 ┌─────────────────────────┐
                 │   ② Theme Engine        │
                 └────────────┬────────────┘
                              ↓
                       找最强题材
                              ↓
                 ┌─────────────────────────┐
                 │   ③ Stock Engine        │
                 └────────────┬────────────┘
                              ↓
                      找板块核心股
                              ↓
                 ┌─────────────────────────┐
                 │   ④ Auction Engine      │
                 └────────────┬────────────┘
                              ↓
                      9:25最终确认
                              ↓
                 ┌─────────────────────────┐
                 │ ⑤ Execution Engine      │
                 └────────────┬────────────┘
                              ↓
                    模拟是否真正买得到
                              ↓
                 ┌─────────────────────────┐
                 │ ⑥ Position Engine       │
                 └────────────┬────────────┘
                              ↓
                 ┌─────────────────────────┐
                 │ ⑦ Exit/Risk Engine      │
                 └─────────────────────────┘
```

------

# 2. 数据库设计

建议至少建立下面 9 张核心表。

## `stock_basic`

```text
stock_code
stock_name
exchange
board
list_date
delist_date
is_st
is_pt
limit_pct
tick_size
total_shares
free_float_shares
industry_l1
industry_l2
```

其中：

```text
board =
MAIN_SH
MAIN_SZ
GEM
STAR
```

不要写死涨跌幅。

------

# 3. `daily_bar`

```text
trade_date
stock_code

open
high
low
close
pre_close

volume
amount

turnover
free_turnover

adj_factor

limit_up_price
limit_down_price

is_limit_up
is_limit_down
```

核心公式：

```python
limit_up_price = round_tick(
    pre_close * (1 + limit_pct)
)
```

这里必须根据股票实际交易规则计算。

------

# 4. `minute_bar`

打板策略最好使用 1 分钟数据。

```text
trade_date
timestamp
stock_code

open
high
low
close

volume
amount

turnover
```

至少保留：

```text
09:25
09:30
09:31
...
15:00
```

因为我们后面要判断：

> **什么时候涨停。**

而不是只知道：

> 今天涨停了。

------

# 5. `limitup_event`

这是整个系统非常重要的一张表。

```text
trade_date
stock_code

limit_up_price

first_limit_time
last_limit_time

break_count
total_break_minutes

final_seal_time

max_seal_amount
close_seal_amount

is_one_word
is_touched_limit

limit_up_volume
limit_up_amount
```

例如：

```text
股票A

09:37 首次涨停
09:48 炸板
10:02 回封
10:17 再次炸板
13:25 回封
15:00 封住

break_count = 2
first_limit_time = 09:37
final_seal_time = 13:25
```

这个信息比：

> “涨停 = 1”

有价值很多。

------

# 6. `theme_daily`

```text
trade_date
theme_id

theme_score

limit_up_count
limit_down_count

board_count

highest_board

promotion_rate

return_1d
return_3d
return_5d

amount
amount_growth

member_count
```

------

# 7. `market_daily`

```text
trade_date

limit_up_count
limit_down_count

first_board_count
second_board_count
third_board_count

highest_board

promotion_rate
break_rate

yesterday_limitup_avg_return
yesterday_lianban_avg_return

market_sentiment
market_regime
```

------

# 8. `auction_snapshot`

这个表专门保存 9:25 数据。

```text
trade_date
stock_code

auction_price
auction_volume
auction_amount

auction_return
auction_turnover

auction_amount_ratio
auction_volume_ratio

price_change_0915_0925
```

特别注意：

**9:25 数据不能放进 T-1 因子。**

它属于：

> T 日盘前实时信息。

因此模型必须明确区分：

```text
PRE_CLOSE_SIGNAL
```

和：

```text
AUCTION_SIGNAL
```

------

# 9. `execution_event`

用于模拟真实成交。

```text
trade_date
stock_code

signal_time

order_price
order_volume

seal_amount_at_order
seal_amount_after_order

queue_estimate

executed_volume
execution_ratio

cancelled_volume

execution_probability
```

------

# 10. `trade_record`

最终策略结果。

```text
trade_id

trade_date
stock_code

entry_time
entry_price
entry_volume

exit_date
exit_time
exit_price

gross_return
commission
stamp_duty
slippage

net_return

holding_minutes
holding_days

market_regime
theme_score
stock_score

exit_reason
```

这样以后才能真正计算：

> Profit Factor、最大回撤、连续亏损、期望值。

------

# 11. Market Regime Engine

市场评分：

```python
market_score = (
    limitup_score
    + limitdown_score
    + promotion_score
    + yesterday_limitup_score
    + yesterday_lianban_score
    + break_rate_score
    + highest_board_score
    + lianban_count_score
)
```

范围：

```text
0~100
```

------

## 状态映射

```python
if score >= 80:
    regime = "VERY_STRONG"

elif score >= 65:
    regime = "STRONG"

elif score >= 50:
    regime = "NORMAL"

elif score >= 35:
    regime = "WEAK"

else:
    regime = "FROZEN"
```

------

# 12. Market Hard Filter

这是硬规则，不参与评分。

```python
if market_score < 35:
    trade_permission = False
```

也就是说：

> **市场极弱时，即使个股评分 95，也不能打板。**

这点必须与普通打分模型区分开。

------

# 13. Theme Engine

每个板块每天计算：

```python
theme_score = (
    limitup_score * 0.20
    + return_3d_score * 0.15
    + return_5d_score * 0.10
    + amount_growth_score * 0.15
    + market_share_score * 0.10
    + lianban_score * 0.10
    + highest_board_score * 0.10
    + promotion_score * 0.10
)
```

最终：

```text
0~100
```

------

# 14. Theme Persistence

这是防止“一日游”的。

计算：

```python
persistence =
    weighted_average(
        theme_score[t-4:t],
        weights=[1,2,3,4,5]
    )
```

最近一天权重最高。

最终：

```text
THEME_SCORE
+
THEME_PERSISTENCE
```

共同决定题材质量。

------

# 15. Stock Score

最终股票评分：

```text
MARKET_POSITION       20
THEME_STRENGTH        15
BOARD_STRUCTURE       10
TURNOVER              10
VOLUME_PRICE           8
BOARD_QUALITY          8
NEXT_DAY_PREMIUM       7
MONEY_FLOW             5
MARKET_CAP              2
AUCTION                15
-------------------------
TOTAL                 100
```

------

# 16. Market Position

```python
if stock_board == theme_highest_board:
    score = 20

elif stock_board == theme_highest_board - 1:
    score = 15

elif stock_board == theme_highest_board - 2:
    score = 8

else:
    score = 0~5
```

再加入：

```text
是否唯一高度
是否板块核心
是否同题材最高换手
是否同题材最高成交额
```

最终得到：

```text
LEADERSHIP_SCORE
```

------

# 17. Board Structure

基础：

```text
1板  = 4
2板  = 10
3板  = 10
4板  = 8
5板  = 5
6板+ = 0
```

但不能机械使用。

增加：

```text
relative_height
```

例如：

```text
市场最高板 = 8

当前股票 = 3板
```

那么：

```text
relative_height_score = low
```

------

# 18. Turnover Engine

定义：

```python
relative_turnover =
    current_turnover /
    median(turnover[-20:])
```

基础：

```text
<0.8       0
0.8~1.2    3
1.2~2.0    7
2.0~3.5    10
3.5~5.0    5
>5.0       0
```

然后根据连板高度做调整。

------

# 19. Volume Price Engine

核心不是：

> 放量就是好。

而是：

```text
价格上涨
+
成交量增加
+
换手增加
+
没有极端爆量
```

例如：

```python
volume_score =
    price_strength
    + volume_expansion
    + turnover_quality
    - extreme_volume_penalty
```

------

# 20. Board Quality Engine

定义：

```python
board_quality = (
    first_limit_score
    + break_score
    + reseal_score
    + seal_amount_score
)
```

例如：

```text
首次封板 < 09:35       +10
09:35~10:00             +8
10:00~11:00             +6
11:00~13:30             +4
13:30~14:30             +2
>14:30                   0
```

炸板：

```text
0次     +10
1次      +7
2次      +4
3次+     0
```

------

# 21. Next Day Premium Engine

这个是 v2.0 的核心创新之一。

对每只股票计算历史：

```python
next_day_open_return
next_day_high_return
next_day_close_return
next_day_negative_probability
```

但注意：

**只能使用过去的数据。**

例如 T 日计算：

```text
T-1及之前所有涨停事件
```

绝对不能使用：

> T+1。

否则直接未来函数。

------

# 22. 更进一步：做“条件历史溢价”

不要简单：

> 这只股票历史涨停后平均 +3%。

而是：

> **类似条件下涨停后表现如何？**

例如：

```text
当前：
3板
机器人
市场情绪72
板块82
换手2.1倍
首次封板09:41
```

那么历史匹配：

```text
3板
机器人
市场情绪65~80
板块75~90
换手1.8~2.5
封板时间09:30~10:00
```

然后统计：

```text
T+1开盘
T+1最高
T+1收盘
```

这比简单历史均值强得多。

后续可以升级成：

> KNN / Gradient Boosting / LightGBM。

------

# 23. Auction Engine

9:25重新计算。

例如：

```python
auction_score = (
    auction_return_score
    + auction_amount_score
    + auction_volume_score
    + auction_stability_score
)
```

但是：

**不能只看竞价涨幅。**

例如：

```text
竞价 +9.8%
```

并不一定比：

```text
竞价 +4.5%
```

好。

------

# 24. 竞价异常过滤

增加：

```python
if auction_return > 0.09 and \
   auction_volume_ratio > extreme_threshold:
       risk_flag = "OVERHEATED"
```

以及：

```python
if auction_return < -0.03:
       reject = True
```

但这些阈值不能直接永久固定，后面需要 walk-forward 优化。

------

# 25. Execution Engine

这是整个系统最重要的技术模块。

不要：

```python
if stock.is_limit_up:
    buy(price=limit_price)
```

这是错误的。

必须：

```python
if limit_up:
    estimate_queue()
    estimate_fill_probability()
    simulate_order()
```

------

# 26. 排队模型

假设：

```text
涨停价：10元

当前封单：
5000万

你的订单：
20万

当日后续成交：
```

估计：

```python
queue_position =
    existing_queue
    + your_order
```

然后：

```python
fill_ratio =
    min(
        available_liquidity / queue_position,
        1
    )
```

这只是第一版。

后面可以用 Level-2 数据进一步优化。

------

# 27. 特别处理一字板

如果：

```text
is_one_word == True
```

则：

```python
execution_probability = very_low
```

而不是：

> 高分 → 自动买入。

因为：

**策略不是预测涨停，而是交易。**

买不到的股票：

> 不应该计入实际收益。

------

# 28. 真实买入规则

最终：

```python
def should_buy(stock, market, theme, auction):

    if market.permission == False:
        return False

    if theme.score < 50:
        return False

    if stock.score < 75:
        return False

    if stock.leadership_score < MIN_LEADERSHIP:
        return False

    if auction.score < MIN_AUCTION:
        return False

    if stock.execution_probability < 0.30:
        return False

    return True
```

------

# 29. 仓位模型

不要固定仓位。

定义：

```python
position =
    base_position
    * market_multiplier
    * score_multiplier
    * execution_multiplier
```

例如：

### 极强市场

```text
市场 ≥80
A级股票

最大 25%
```

### 强市场

```text
65~80

最大 20%
```

### 正常

```text
50~65

最大 10%
```

### <50

```text
禁止新增
```

------

# 30. 单票限制

硬规则：

```text
MAX_SINGLE_POSITION = 30%
MAX_TOTAL_POSITIONS = 4
```

并且：

```text
同一题材总仓位 <= 50%
```

避免：

> 买了四只“不同股票”，实际上全押一个题材。

------

# 31. Exit Engine

卖出分为：

```text
A. 止盈
B. 止损
C. 结构破坏
D. 市场退潮
E. 时间退出
```

------

# 32. T+1 时间退出

打板策略不能无限持有。

默认：

```text
T+1 必须重新评估
T+2 仍未重新转强 → 强制退出
```

也就是说：

> 这个模型不是波段策略。

------

# 33. 结构止损

例如：

```python
if price < yesterday_close:
    risk += 1
```

再：

```python
if price < key_support:
    exit()
```

以及：

```python
if theme_score collapses:
    exit()
```

------

# 34. 市场退潮退出

如果：

```text
MARKET_SENTIMENT
72 → 43
```

同时：

```text
promotion_rate ↓
break_rate ↑
highest_board ↓
```

则：

```text
REDUCE_POSITION
```

如果进一步：

```text
MARKET_SENTIMENT < 35
```

则：

```text
EXIT_WEAK_POSITIONS
```

------

# 35. 最终交易状态机

我建议 Agent 不要只返回 `BUY/SELL`。

使用：

```text
WATCH
↓
QUALIFIED
↓
WAIT_AUCTION
↓
READY
↓
ORDERED
↓
PARTIAL_FILLED
↓
FILLED
↓
HOLD
↓
EXIT_PENDING
↓
CLOSED
```

这会让后面的实盘系统非常容易扩展。

------

# 36. JSON Schema

最终 Agent 可以接收：

```json
{
  "date": "2026-09-07",
  "stock": {
    "code": "000001",
    "board": "MAIN_SZ",
    "board_count": 3
  },
  "market": {
    "sentiment": 72.4,
    "regime": "STRONG",
    "trade_permission": true
  },
  "theme": {
    "name": "example_theme",
    "score": 81.3,
    "persistence": 76.5,
    "highest_board": 5
  },
  "stock_factors": {
    "leadership": 18.5,
    "board_structure": 9.5,
    "turnover": 8.7,
    "volume_price": 7.2,
    "board_quality": 7.6,
    "next_day_premium": 6.1,
    "money_flow": 4.0,
    "market_cap": 2.0
  },
  "auction": {
    "return": 0.045,
    "amount_ratio": 1.82,
    "score": 12.6
  },
  "execution": {
    "probability": 0.68
  }
}
```

最终：

```json
{
  "stock_score": 85.2,
  "signal": "BUY",
  "position": 0.20,
  "risk": "MEDIUM"
}
```

------

# 37. Python核心接口

最终 Agent 的核心接口可以设计成：

```python
class LimitUpModelV2:

    def calculate_market_regime(
        self,
        market_data
    ):
        pass

    def calculate_theme_score(
        self,
        theme_data,
        market_state
    ):
        pass

    def calculate_stock_score(
        self,
        stock_data,
        theme_state,
        market_state
    ):
        pass

    def calculate_auction_score(
        self,
        auction_data,
        stock_state
    ):
        pass

    def estimate_execution_probability(
        self,
        orderbook,
        order
    ):
        pass

    def generate_signal(
        self,
        market,
        theme,
        stock,
        auction
    ):
        pass

    def generate_exit_signal(
        self,
        position,
        market,
        theme,
        stock
    ):
        pass
```

------

# 38. 回测引擎

回测绝对不要写成：

```python
for date in dates:
    signal = model.predict(data[date])
```

然后直接拿：

```text
close[date]
```

买入。

正确结构：

```text
T-1
 ↓
生成候选池
 ↓
T日 09:25
 ↓
更新竞价数据
 ↓
产生最终信号
 ↓
T日分钟级撮合
 ↓
成交/未成交
 ↓
持仓
 ↓
T+1分钟级退出
 ↓
记录交易
```

------

# 39. 严格数据边界

这是防止未来函数的核心：

| 数据    | T-1盘后 | T日9:25 | T日盘中 | T+1  |
| ------- | ------- | ------- | ------- | ---- |
| T-1日线 | ✅       | ✅       | ✅       | ✅    |
| T日竞价 | ❌       | ✅       | ✅       | ❌    |
| T日成交 | ❌       | ❌       | ✅       | ❌    |
| T日收盘 | ❌       | ❌       | ❌       | ✅    |
| T+1行情 | ❌       | ❌       | ❌       | 标签 |

任何模型变量都必须记录：

```text
feature_timestamp
availability_timestamp
```

------

# 40. 这一点尤其重要

例如：

```text
龙虎榜
```

不能简单写：

```text
trade_date = T-1
```

还必须确认：

> **这条龙虎榜数据到底什么时候对市场可见。**

同理：

> 财报

不能使用：

```text
report_period
```

而应该使用：

```text
publication_time
```

这是专业回测和普通“历史数据回测”的区别。

------

# 41. 回测输出

每天输出：

```json
{
  "date": "2026-09-07",

  "market": {
    "score": 72.4,
    "regime": "STRONG"
  },

  "candidates": [
    {
      "code": "xxxxxx",
      "score": 88.3,
      "signal": "BUY",
      "execution_probability": 0.72
    },
    {
      "code": "xxxxxx",
      "score": 82.7,
      "signal": "BUY",
      "execution_probability": 0.51
    }
  ],

  "portfolio": {
    "positions": 2,
    "exposure": 0.35
  }
}
```

------

# 42. 最终绩效指标

必须至少输出：

```text
Total Return
CAGR
Max Drawdown
Sharpe
Sortino

Win Rate
Average Win
Average Loss
Profit Factor

Expectancy
Average Holding Time

T+1 Average Return
T+1 Median Return

T+1 Win Rate
T+2 Win Rate

Maximum Consecutive Losses

Execution Rate
Partial Fill Rate
Missed Trade Rate
```

其中我最看重：

> **Expectancy + Profit Factor + Max Drawdown + Execution Rate**

而不是单纯收益率。

------

# 43. 交易期望值

最终判断策略是否值得实盘，可以用：

E=P(win)×AvgWin−P(loss)×AvgLossE = P(win)\times AvgWin-P(loss)\times AvgLoss

例如：

```text
胜率 = 48%

平均盈利 = +6%

平均亏损 = -4%
```

则：

E=0.48×6%−0.52×4%E=0.48\times6\%-0.52\times4\%

得到：

> **+0.80% / trade**

这才是真正有意义的东西。

------

# 44. 你原来的 46.99% 怎么处理？

**不要先入为主地认为 46.99% 很差。**

假如：

```text
胜率 47%
平均盈利 +8%
平均亏损 -4%
```

实际上可能非常赚钱。

反过来：

```text
胜率 60%
平均盈利 +2%
平均亏损 -5%
```

反而可能亏钱。

所以 v2.0 不再把：

> 46.99%

作为核心结论。

必须重新计算：

> **条件胜率 + 盈亏比 + 实际成交率。**

------

# 45. 第一版不要上机器学习

这一点我反而非常建议你克制。

先使用：

```text
Rule-based
+
Factor Score
```

跑出：

> v2.0 baseline。

然后再做：

```text
v2.1
LightGBM

v2.2
XGBoost

v2.3
ensemble
```

否则一开始就机器学习，很容易得到：

> 回测神策略。

实盘：

> 直接失效。

------

# 46. 我建议的开发顺序

不要一次性写完。

按照：

```text
Phase 1
数据层
↓
Phase 2
涨停事件识别
↓
Phase 3
市场情绪
↓
Phase 4
板块强度
↓
Phase 5
个股评分
↓
Phase 6
竞价
↓
Phase 7
撮合
↓
Phase 8
T+1退出
↓
Phase 9
Walk-forward
↓
Phase 10
参数优化
```

逐层验证。

------

# 47. 第一阶段验收标准

**先不要追求赚钱。**

第一阶段只验证：

### 涨停识别是否正确

随机抽取 5000 个交易日×股票样本，检查：

```text
涨停识别准确率
首次封板时间
炸板次数
最终封板时间
```

### 市场情绪是否正确

人工抽查：

```text
牛市
震荡
冰点
退潮
```

### 板块排名是否合理

看看模型排出来的 Top 10 板块是否符合历史市场结构。

------

# 48. 第二阶段才看策略收益

然后比较：

```text
v1.0
vs
v2.0
```

至少做四组：

```text
A：原策略

B：v2市场过滤

C：v2市场+板块

D：完整v2
```

如果：

```text
A → B → C → D
```

收益、回撤、Profit Factor逐步改善，

说明你的新增因子真正有贡献。

------

# 49. 最终还要做一个“反事实测试”

例如：

> 删除市场情绪因子。

看看结果。

再：

> 删除板块强度。

再：

> 删除龙头因子。

再：

> 删除竞价。

如果发现：

```text
删除PE：
策略几乎不受影响

删除市场情绪：
最大回撤暴增

删除龙头：
Profit Factor下降

删除竞价：
胜率下降
```

你就知道：

> **哪些因子真的有用。**

而不是凭直觉认为某个因子重要。

------

# 50. 我给这套 v2.0 定一个非常明确的目标

不要追求：

> **“100%预测涨停。”**

也不要追求：

> **“每天都交易。”**

真正目标是：

> **在适合接力的市场环境中，只做最强板块中的核心个股，并且只参与具有实际成交可能、T+1具有正期望的交易。**

这才是这套系统真正的 Alpha 来源。

------

### 一个重要提醒

这套东西属于高风险的短线交易系统，**回测结果不等于未来收益，也不能保证实盘盈利**。尤其打板策略会受到排队、滑点、撤单、流动性、监管与交易规则变化的影响。当前交易规则本身也在持续调整，所以数据层一定要做成**规则参数化**，而不是把某一天的制度硬编码进去。比如深交所 2026 年规则已经明确主板 10%、创业板 20%，上交所 2026 年规则也明确科创板 20%，并对主板风险警示股票的限制作了调整。([深交所文档](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf?utm_source=chatgpt.com))

**下一步最值得做的不是继续增加因子，而是直接写 `v2.0 Backtest Engine`。**

也就是下一步我可以直接给你：

```text
project/
├── data/
├── config/
│   └── model_v2.yaml
├── factors/
│   ├── market.py
│   ├── theme.py
│   ├── leadership.py
│   ├── turnover.py
│   ├── volume_price.py
│   ├── board_quality.py
│   ├── premium.py
│   └── auction.py
├── execution/
│   ├── queue.py
│   ├── matcher.py
│   └── slippage.py
├── strategy/
│   ├── signal.py
│   ├── position.py
│   └── exit.py
├── backtest/
│   ├── engine.py
│   ├── metrics.py
│   └── walk_forward.py
└── main.py
```

并把**每一个 Python 类、函数、输入字段、输出字段和公式全部定义出来**，形成可以直接开始编码的 **`LimitUp_Factor_Model_v2.0` 开发规范**。



你给出基本的定义和说明吧，我去找agent做具体开发



可以。你去找 Agent 开发的话，**不需要把实现细节写死**，反而应该给 Agent 一份“策略定义书”，让它自己决定代码架构和具体实现。

下面这份我建议你直接复制给 Agent。它定义的是**策略思想、因子、计算口径、交易规则和回测原则**。

------

# LimitUp_Factor_Model v2.0

## A股涨停接力量化策略——策略定义与开发说明

### 一、策略定位

本策略是一套针对 A 股短线涨停/连板行情的**事件驱动型量化交易策略**。

核心目标：

> 在适合短线接力的市场环境中，从最强题材中筛选市场地位较高、量价结构健康、封板质量较好且具有历史次日正向溢价的股票，在 T 日进行涨停接力，并主要通过 T+1 完成退出。

策略不是中长线价值投资策略，也不是预测个股未来长期收益的模型。

核心预测周期：

```text
T日：发现、确认、买入
T+1：主要退出
T+2：次要退出
T+5：统计评价
```

------

# 二、核心思想

策略采用四层筛选：

```text
市场环境
    ↓
板块强弱
    ↓
个股地位
    ↓
交易执行
```

最终不是简单寻找“高分股票”，而是寻找：

> **当前市场允许交易 → 当前最强题材 → 题材核心个股 → 有实际买入机会 → T+1具有正期望**

的交易机会。

------

# 三、策略必须解决的五个问题

Agent 开发时必须围绕以下五个问题设计：

### 1. 今天适不适合打板？

由市场情绪模型决定。

### 2. 今天应该做哪个题材？

由板块强度模型决定。

### 3. 这个题材里面应该买谁？

由市场地位/龙头模型决定。

### 4. 这个股票到底能不能买到？

由竞价和成交模拟模型决定。

### 5. 买到以后什么时候卖？

由 T+1/T+2 退出模型决定。

------

# 四、第一层：市场情绪模型

建立：

```text
MARKET_SENTIMENT
```

范围：

```text
0~100
```

建议包含：

| 因子                    | 建议权重 |
| ----------------------- | -------- |
| 涨停数量                | 15       |
| 跌停数量                | 10       |
| 涨停晋级率              | 15       |
| 昨日涨停股平均 T+1 收益 | 15       |
| 昨日连板股平均 T+1 收益 | 15       |
| 炸板率                  | 10       |
| 市场最高连板高度        | 10       |
| 连板股数量              | 10       |

最终：

```text
MARKET_SENTIMENT = 0~100
```

------

## 市场状态

```text
80~100    VERY_STRONG
65~80     STRONG
50~65     NORMAL
35~50     WEAK
0~35      FROZEN
```

------

## 市场交易权限

这是硬过滤条件，不参与个股评分。

```text
VERY_STRONG → 正常交易
STRONG      → 正常交易
NORMAL      → 精选交易
WEAK        → 轻仓/谨慎
FROZEN      → 禁止新增打板
```

尤其要求：

> 如果 MARKET_SENTIMENT < 35，则不得产生新的打板买入信号。

------

# 五、第二层：板块强度模型

取消固定“热点行业名单”。

不要定义：

```text
电子
医药
计算机
机械
……
```

为永久热点。

而应该每天动态计算：

```text
THEME_SCORE
```

范围：

```text
0~100
```

建议因素：

| 因子                     | 权重 |
| ------------------------ | ---- |
| 板块涨停数量             | 20   |
| 板块 3 日收益            | 15   |
| 板块 5 日收益            | 10   |
| 板块成交额增长           | 15   |
| 板块涨停数量占全市场比例 | 10   |
| 板块连板数量             | 10   |
| 板块最高板高度           | 10   |
| 板块晋级率               | 10   |

------

# 六、板块持续性

增加：

```text
THEME_PERSISTENCE
```

用于区分：

> 真正主线

和：

> 一日游题材。

建议综合过去 5 个交易日：

```text
板块涨停数量
板块涨幅
板块成交额
板块连板数量
板块晋级率
```

最近交易日权重最高。

最终：

```text
THEME_SCORE
+
THEME_PERSISTENCE
```

共同评价板块。

------

# 七、第三层：个股模型

个股总分：

```text
STOCK_SCORE = 0~100
```

建议权重：

| 因子         | 权重    |
| ------------ | ------- |
| 市场地位     | 20      |
| 板块强度     | 15      |
| 连板结构     | 10      |
| 换手结构     | 10      |
| 量价关系     | 8       |
| 封板质量     | 8       |
| 历史次日溢价 | 7       |
| 资金结构     | 5       |
| 市值         | 2       |
| 竞价强度     | 15      |
| **合计**     | **100** |

------

# 八、市场地位因子

这是最重要的个股因子之一。

定义：

```text
LEADERSHIP_SCORE
```

重点考虑：

- 是否为板块最高板
- 与板块最高板的高度差
- 是否为唯一高度
- 是否为板块核心
- 是否为同题材成交额核心
- 是否为同题材换手核心

基本逻辑：

```text
板块最高板       → 最高评分
板块第二高度     → 次高评分
板块第三高度     → 中等评分
普通跟风股       → 低评分
```

必须避免：

> 只因为股票自身是 3 板，就认为它是强股。

必须考虑：

> **它在整个板块中的相对地位。**

------

# 九、连板结构因子

定义：

```text
BOARD_STRUCTURE_SCORE
```

基础建议：

```text
1板   → 4
2板   → 10
3板   → 10
4板   → 8
5板   → 5
6板+  → 0
```

但上述只是基础分。

必须结合：

```text
市场最高板
板块最高板
当前股票连板高度
```

计算：

```text
RELATIVE_HEIGHT
```

例如：

```text
市场最高板 = 8
股票 = 3板
```

和：

```text
市场最高板 = 3
股票 = 3板
```

不能得到相同评价。

------

# 十、换手因子

定义：

```text
TURNOVER_SCORE
```

不要简单固定：

> 换手率 15%~45%。

建议计算：

```text
RELATIVE_TURNOVER =
当前换手率 /
过去20日换手率中位数
```

重点寻找：

> 相对于自身历史正常水平出现合理放量换手的股票。

同时识别：

```text
极低换手
正常换手
强换手
过热换手
极端爆量
```

------

# 十一、量价因子

定义：

```text
VOLUME_PRICE_SCORE
```

主要评价：

```text
价格变化
成交量变化
换手变化
成交额变化
```

理想结构：

```text
上涨
+
成交量合理增加
+
换手增加
+
没有极端爆量
```

需要特别惩罚：

```text
价格上涨
+
成交量突然极端放大
+
换手率极端
```

因为这种结构可能意味着：

> 情绪高潮或者资金兑现。

------

# 十二、封板质量

定义：

```text
BOARD_QUALITY_SCORE
```

至少考虑：

- 首次封板时间
- 最终封板时间
- 炸板次数
- 炸板持续时间
- 回封速度
- 封单金额
- 封单变化

------

## 封板时间

一般情况下：

```text
越早封板 → 越强
越晚封板 → 越弱
```

但：

> **一字板不能简单等同于高质量封板。**

必须结合：

```text
是否有换手
成交额
成交量
封单
实际成交机会
```

------

# 十三、炸板因子

定义：

```text
BREAK_BOARD_SCORE
```

核心变量：

```text
break_count
break_duration
reseal_time
```

例如：

```text
0次炸板       → 强
1次快速回封   → 较强
2次回封       → 中等
多次炸板      → 弱
```

同时：

> 炸板后快速回封通常优于长时间无法回封。

------

# 十四、历史次日溢价

定义：

```text
NEXT_DAY_PREMIUM_SCORE
```

统计股票历史涨停事件：

```text
T+1开盘收益
T+1最高收益
T+1收盘收益
T+1负收益概率
```

但是：

> **只能使用当前时间点之前已经发生的历史事件。**

不能产生任何未来函数。

进一步可以做条件匹配：

```text
相同连板高度
+
相似市场情绪
+
相似板块强度
+
相似换手
+
相似封板时间
```

然后统计历史相似场景下的 T+1 收益。

------

# 十五、资金结构

定义：

```text
MONEY_FLOW_SCORE
```

龙虎榜不再简单规定：

> 游资买入 = 好
> 机构卖出 = 好。

应该综合：

```text
龙虎榜净买入/成交额
买一金额占比
买一+买二集中度
机构净买入比例
活跃营业部
```

龙虎榜数据还必须考虑：

> **数据实际披露时间。**

不能因为“交易日是 T-1”就自动认为 T-1 盘后一定可用。

------

# 十六、市值

市值只保留为辅助因子。

建议：

```text
20~50亿       +2
50~100亿      +1
100~200亿      0
>200亿        -1
```

不要让市值成为核心买入理由。

------

# 十七、PE

v2.0：

> **PE 不参与评分。**

可以保留在数据层，但不要作为打板买入因子。

原因：

> 打板模型的核心变量是资金、情绪、题材和市场地位，而不是静态估值。

------

# 十八、竞价模型

T 日 9:25 后重新计算。

定义：

```text
AUCTION_SCORE
```

考虑：

- 竞价涨幅
- 竞价成交量
- 竞价成交额
- 竞价换手
- 竞价成交额/昨日成交额
- 竞价价格稳定性

注意：

```text
T-1模型
```

和：

```text
T日9:25模型
```

必须严格区分。

------

# 十九、竞价不能只看涨幅

例如：

```text
竞价 +9.8%
```

不一定比：

```text
竞价 +4.5%
```

好。

必须判断：

```text
竞价价格
+
成交量
+
成交额
+
板块表现
+
龙头表现
```

是否匹配。

特别警惕：

> 极端高开 + 极端放量 + 板块弱化。

------

# 二十、硬过滤器

无论股票评分多高，以下条件成立时禁止买入：

```text
市场情绪 < 35
```

或者：

```text
板块评分过低
```

或者：

```text
流动性不足
```

或者：

```text
存在明显交易风险
```

或者：

```text
一字板且实际成交概率极低
```

或者：

```text
极端爆量
```

或者：

```text
无法可靠获得必要数据
```

核心原则：

> **宁可错过，不要强行交易。**

------

# 二十一、最终买入条件

建议：

```text
MARKET_SENTIMENT >= 35
THEME_SCORE >= 50
STOCK_SCORE >= 75
LEADERSHIP_SCORE >= 最低阈值
AUCTION_SCORE >= 最低阈值
EXECUTION_PROBABILITY >= 30%
```

以上条件全部满足，才产生：

```text
BUY
```

------

# 二十二、信号等级

### A级

```text
STOCK_SCORE >= 85
```

且：

```text
市场强
板块强
市场地位强
```

→ 正常仓位。

### B级

```text
75~85
```

→ 半仓或小仓位。

### C级

```text
70~75
```

→ 只观察，不主动交易。

------

# 二十三、仓位

建议采用动态仓位：

```text
市场情绪
×
股票评分
×
交易成交概率
```

综合确定。

建议：

```text
单票最大仓位：30%
最大持仓数量：4只
同一题材总仓位：≤50%
```

具体数值允许 Agent 在回测阶段优化。

------

# 二十四、成交模拟

这是整个系统必须重点开发的部分。

禁止：

```python
涨停 = 买入成功
```

必须模拟：

```text
订单提交时间
↓
当时封单
↓
已有排队量
↓
后续成交量
↓
封单变化
↓
实际可成交量
↓
成交概率
```

输出：

```text
EXECUTION_PROBABILITY
```

以及：

```text
EXECUTED_VOLUME
EXECUTION_RATIO
```

------

# 二十五、一字板处理

如果：

```text
ONE_WORD = True
```

不能因为股票评分高就默认买入。

必须判断：

> **实际是否存在成交机会。**

回测中：

> 买不到 = 没有交易。

不能把“理论收益”计入策略收益。

------

# 二十六、卖出模型

主要评价：

```text
T+1
```

辅助：

```text
T+2
```

不建议持仓超过 T+2 后仍然无条件持有。

------

## 卖出原因

定义：

```text
TAKE_PROFIT
STOP_LOSS
STRUCTURE_BREAK
MARKET_EXIT
THEME_EXIT
TIME_EXIT
```

------

# 二十七、结构止损

不要简单：

```text
跌5% → 卖
```

而应该判断：

```text
是否跌破关键价格
+
板块是否走弱
+
龙头是否走弱
+
个股是否失去承接
```

------

# 二十八、市场退潮退出

如果：

```text
MARKET_SENTIMENT
快速下降
```

同时：

```text
晋级率下降
炸板率上升
最高板下降
昨日涨停股表现恶化
```

则：

```text
减少新仓位
```

进一步恶化：

```text
MARKET_SENTIMENT < 35
```

则：

> 禁止新增打板。

已有弱势仓位允许触发退出。

------

# 二十九、时间退出

如果 T+1 没有出现预期的强势表现：

> 优先退出。

如果 T+2 仍然没有重新转强：

> 原则上退出。

因为：

> 该策略的 Alpha 主要来自短期情绪和资金接力，而不是长期基本面。

------

# 三十、回测必须使用事件驱动模式

正确流程：

```text
T-1 收盘
↓
生成候选股票
↓
计算市场/板块/个股因子
↓
T日 9:25
↓
获取竞价数据
↓
更新最终信号
↓
T日盘中
↓
模拟订单成交
↓
建立仓位
↓
T+1
↓
分钟级退出
↓
记录收益
```

禁止：

```text
看到T日收盘涨停
↓
假设T日收盘可以买到
```

------

# 三十一、未来函数控制

每一个 Feature 必须记录：

```text
feature_value
feature_timestamp
availability_timestamp
```

特别注意：

- 龙虎榜
- 财报
- 股东数据
- 题材分类
- 监管信息
- 复权数据

必须按照：

> **市场实际知道信息的时间**

处理。

而不是按照：

> 数据对应的报告日期。

------

# 三十二、涨停价格必须动态计算

不要写死：

```python
limit_up = close * 1.10
```

而应该根据：

```text
交易所
板块
股票状态
交易规则
前收盘价
```

动态计算。

数据层必须保存：

```text
limit_up_price
limit_down_price
limit_pct
```

并处理特殊股票状态。

------

# 三十三、核心回测指标

至少输出：

```text
Total Return
CAGR
Maximum Drawdown

Win Rate
Average Win
Average Loss
Profit Factor
Expectancy

T+1 Average Return
T+1 Median Return
T+1 Win Rate

T+2 Average Return

Maximum Consecutive Losses

Execution Rate
Partial Fill Rate
Missed Trade Rate
```

其中最重要：

> **Expectancy**

> **Profit Factor**

> **Maximum Drawdown**

> **Execution Rate**

------

# 三十四、期望收益

核心公式：

E=P(win)×AvgWin−P(loss)×AvgLossE=P(win)\times AvgWin-P(loss)\times AvgLoss

例如：

```text
胜率 48%
平均盈利 +7%
平均亏损 -4%
```

则：

E=0.48×7%−0.52×4%E=0.48\times7\%-0.52\times4\%

得到：

```text
+1.28%
```

这个指标比单纯胜率更加重要。

------

# 三十五、Walk-forward 回测

禁止：

```text
2019~2026全部数据
↓
优化参数
↓
宣布策略有效
```

应该：

```text
训练区间
↓
测试区间
↓
滚动前进
↓
重新训练
↓
重新测试
```

最终只看：

> **Out-of-Sample Performance**

------

# 三十六、策略消融测试

必须至少测试：

```text
Model A
原始 v1
Model B
v2 + 市场情绪
Model C
v2 + 市场情绪 + 板块
Model D
完整 v2
```

以及删除测试：

```text
删除市场情绪
删除板块
删除龙头
删除竞价
删除次日溢价
删除龙虎榜
```

观察：

```text
收益
最大回撤
Profit Factor
Expectancy
```

变化。

------

# 三十七、不要一开始使用机器学习

第一阶段：

```text
Rule-based
+
Factor Score
```

先建立：

> **v2.0 Baseline**

确认策略本身有统计优势以后，再考虑：

```text
LightGBM
XGBoost
Random Forest
```

机器学习的目标不是：

> 预测涨停。

而应该预测：

```text
P(T+1 positive return)
```

或者：

```text
Expected T+1 return
```

最终可以形成：

```text
Rule Filter
+
ML Ranking
```

架构。

------

# 三十八、Agent 最终应该输出什么

每日候选结果建议：

```json
{
  "market_regime": "STRONG",
  "market_score": 72.4,

  "themes": [
    {
      "name": "THEME_A",
      "score": 84.2,
      "persistence": 79.1
    }
  ],

  "candidates": [
    {
      "stock": "XXXXXX",
      "stock_score": 87.3,
      "leadership_score": 19.2,
      "theme_score": 84.2,
      "auction_score": 13.1,
      "execution_probability": 0.72,

      "signal": "BUY",
      "position": 0.20,

      "risk": "MEDIUM"
    }
  ]
}
```

------

# 三十九、最重要的策略原则

把下面这几句话直接写进 Agent 的 system prompt：

> **第一原则：市场不适合打板时，不交易。**

> **第二原则：不追求股票数量，只寻找最强题材中的核心股票。**

> **第三原则：高分不等于可以买，必须考虑实际成交概率。**

> **第四原则：不能使用任何未来信息。**

> **第五原则：回测不能假设一字板或封死涨停板可以无条件成交。**

> **第六原则：打板策略的核心评价指标是 T+1 交易结果，而不是 T+60 长期收益。**

> **第七原则：所有参数必须经过 Walk-forward / Out-of-Sample 验证，不允许仅根据全历史数据优化。**

> **第八原则：任何单一因子都不能成为买入的充分条件。**

------

# 四十、最终策略可以浓缩成一句话

> **只在市场情绪允许的时候，参与最强题材；只做题材中的高地位股票；只做具有合理换手和封板结构的机会；9:25后结合竞价确认；只有存在真实成交可能才下单；主要博弈 T+1 溢价；市场退潮立即降低风险。**

这就是我建议你交给 Agent 的 **v2.0 基本定义**。

**不要让 Agent 一上来就“优化参数”。**第一阶段应该让它先完成一个能跑的 baseline，然后拿你现有的 v1.0 与 v2.0 做严格的 **同数据、同交易成本、同成交规则** 对比。只有证明 v2.0 在样本外确实改善了 `Expectancy / Profit Factor / Max Drawdown`，才值得进入下一轮优化。