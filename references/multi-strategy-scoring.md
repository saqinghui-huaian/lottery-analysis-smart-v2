# Multi-Strategy Scoring System v3 (多策略综合评分 v3)

> **This scoring system is designed for 3-digit lotteries (福彩3D, 排列三).**
> For 大乐透 (5+2 format), see `references/dlt-analysis.md` for the adapted methodology.

## ⚠️ 数学基础 (必须理解)

**彩票开奖是独立随机事件。** 每期开奖号码与历史数据无关。以下统计指标用于
"描述历史分布"而非"预测未来"。遗漏回补是概率错觉（赌徒谬误），但作为
用户要求的分析维度，我们提供严谨的数学框架。

### 理论概率（3位数字，每位独立均匀分布 0-9）

| 指标 | 理论值 | 推导 |
|:---|:---|:---|
| 单个号码出现概率 | p = 1/10 = 10% | 每位10个数字等概率 |
| 遗漏期望 | E[miss] = 1/p - 1 = 9期 | 几何分布 |
| 遗漏方差 | Var[miss] = (1-p)/p² = 90 | 几何分布方差 |
| 遗漏标准差 | σ[miss] = √90 ≈ 9.49期 | 标准差 |
| P(遗漏≥15期) | 0.9^15 = 20.6% | (1-p)^k |
| P(遗漏≥20期) | 0.9^20 = 12.2% | (1-p)^k |
| P(遗漏≥30期) | 0.9^30 = 4.2% | (1-p)^k |
| 重号概率(至少1位) | 1-(0.9)^3 = 27.1% | 补集 |
| 连号概率 | 43.8% | 枚举438/1000 |
| 组六概率 | 72.0% = 720/1000 | 枚举 |
| 组三概率 | 27.0% = 270/1000 | 枚举 |
| 豹子概率 | 1.0% = 10/1000 | 枚举 |
| 和值均值 | 13.5 | 3 × (0+9)/2 |
| 和值方差 | 6.75 | 3 × (9²-1)/12 |
| 和值标准差 | σ ≈ 2.60 | √6.75 |
| 和值众数 | 13, 14 (各75次) | 枚举 |
| 奇偶比 2:1 或 1:2 | 各37.5% | C(3,1)×0.5^3 |
| 大小比 2:1 或 1:2 | 各37.5% | 同上 |
| 0路(0,3,6,9)概率 | 40% | 4/10 |
| 1路(1,4,7)概率 | 30% | 3/10 |
| 2路(2,5,8)概率 | 30% | 3/10 |

### 统计学概念应用

#### 1. 期望值与方差
- **期望值 E[X]**: 长期平均结果。如和值期望=13.5，跨度期望≈4.5
- **方差 Var[X]**: 数据离散程度。方差越大，波动越大
- **标准差 σ**: 方差的平方根，更直观的离散度量

#### 2. 置信区间（95%）
- **和值置信区间**: 13.5 ± 1.96×2.60 ≈ [8.4, 18.6]
- **遗漏置信区间**: 9 ± 1.96×9.49 ≈ [0, 27.6]（截断为0）
- **应用**: 超出95%置信区间的值可视为"统计异常"

#### 3. 卡方检验（χ²检验）
- **用途**: 检验观测分布是否符合理论分布
- **公式**: χ² = Σ[(O-E)²/E]，O=观测频数，E=期望频数
- **自由度**: k-1（k为类别数）
- **临界值**: χ²(0.05, 9) = 16.92（10个数字，95%置信）

#### 4. 大数定律
- **含义**: 样本量越大，样本均值越接近期望值
- **应用**: 130期数据足以让频率稳定在理论值附近
- **注意**: 大数定律不适用于单次预测

#### 5. 中心极限定理
- **含义**: 大量独立随机变量之和近似正态分布
- **应用**: 和值分布近似正态（均值13.5，标准差2.60）

### 和值理论分布

| 和值范围 | 概率 | 说明 |
|:---|:---|:---|
| 0-6 (小) | 8.4% | 低频区 |
| 7-13 (中) | 41.6% | 高频区(含均值13.5) |
| 14-20 (大) | 41.6% | 高频区 |
| 21-27 (超大) | 8.4% | 低频区 |

### 跨度理论分布

| 跨度 | 概率 | 累计概率 |
|:---|:---|:---|
| 0 | 1.0% | 1.0% |
| 1 | 2.8% | 3.8% |
| 2 | 4.6% | 8.4% |
| 3 | 6.4% | 14.8% |
| 4 | 8.2% | 23.0% |
| 5 | 10.0% | 33.0% |
| 6 | 11.8% | 44.8% |
| 7 | 13.6% | 58.4% |
| 8 | 15.4% | 73.8% |
| 9 | 26.2% | 100.0% |

**注意**: 跨度9概率最高（26.2%），因为包含900, 801, 702等多种组合。

## ⚠️ v5关键改进 (vs v4)

1. **遗漏阈值修正**: v4用≥8期(43%概率，太常见)，v5改为≥15期(20.6%)
2. **Markov链转移概率**: 上期某位出X时本期某位出Y的条件概率（注意：对随机
   事件无预测价值，但作为描述性统计保留）
3. **趋势方向分析**: 近5期vs近50期频率差值，识别短期波动
4. **组三形态预测**: 当组三间隔超过平均间隔(约3.7期)时，加入组三候选
5. **候选策略扩展**: 12种独立策略（v5新增3种专业维度策略）
6. **组选形态概率修正**: 豹子1%(非5%)、组三27%(非35%)、组六72%(非60%)
7. **奇偶比修正**: 2:1/1:2各37.5%(非30%)
8. **新增专业维度**: 复隔中分析、和值5维分析、跨度5维分析（参考中彩网专业分析师）
9. **新增统计检验**: 卡方检验验证分布均匀性
10. **增强置信区间**: 95%置信区间作为异常值判断标准

## 核心统计指标

```python
from collections import Counter

def compute_context(data):
    """Compute all statistical context from draw data.
    data: list of (period, bai, shi, ge) tuples, newest first.
    """
    ctx = {}
    n = len(data)
    
    # === 1. 各位频率 (近20/50/100期) ===
    ctx['freq20'] = [Counter(), Counter(), Counter()]
    ctx['freq50'] = [Counter(), Counter(), Counter()]
    ctx['freq100'] = [Counter(), Counter(), Counter()]
    for d in data[:20]:
        for pos in range(3): ctx['freq20'][pos][d[pos+1]] += 1
    for d in data[:50]:
        for pos in range(3): ctx['freq50'][pos][d[pos+1]] += 1
    for d in data[:100]:
        for pos in range(3): ctx['freq100'][pos][d[pos+1]] += 1
    
    # === 2. 加权热度 (近20期×5, 20-50期×3, 50-100期×1) ===
    ctx['weighted'] = Counter()
    for d in data[:20]:
        for x in [d[1],d[2],d[3]]: ctx['weighted'][x] += 5
    for d in data[20:50]:
        for x in [d[1],d[2],d[3]]: ctx['weighted'][x] += 3
    for d in data[50:100]:
        for x in [d[1],d[2],d[3]]: ctx['weighted'][x] += 1
    
    # === 3. 遗漏值 (距上次出现的期数) ===
    # 几何分布: E[miss]=9, P(≥15)=20.6%, P(≥20)=12.2%
    ctx['miss'] = [{},{},{}]
    for digit in range(10):
        for pos in range(3):
            for i, d in enumerate(data):
                if d[pos+1] == digit:
                    ctx['miss'][pos][digit] = i
                    break
            else:
                ctx['miss'][pos][digit] = n
    
    # === 4. 和值统计 (理论均值=13.5) ===
    sums = [d[1]+d[2]+d[3] for d in data]
    ctx['hz_avg'] = sum(sums[:50]) / min(50, n)
    ctx['hz_std'] = (sum((s - ctx['hz_avg'])**2 for s in sums[:50]) / min(50, n)) ** 0.5
    
    # === 5. 跨度统计 ===
    spans = [max(d[1],d[2],d[3]) - min(d[1],d[2],d[3]) for d in data]
    ctx['kd_freq'] = Counter(spans[:50])
    ctx['kd_avg'] = sum(spans[:50]) / min(50, n)
    
    # === 6. 012路统计 (注意: 0路4个数字40%, 1路/2路各3个30%) ===
    def road(x): return x % 3
    ctx['road20'] = [Counter(), Counter(), Counter()]
    for d in data[:20]:
        for pos in range(3): ctx['road20'][pos][road(d[pos+1])] += 1
    
    # === 7. 奇偶统计 (理论: 每位50/50) ===
    ctx['odd_cnt'] = 0
    ctx['even_cnt'] = 0
    for d in data[:20]:
        for x in [d[1],d[2],d[3]]:
            if x % 2 == 1: ctx['odd_cnt'] += 1
            else: ctx['even_cnt'] += 1
    
    # === 8. 大小统计 (理论: 每位50/50, 5-9为大) ===
    ctx['big_cnt'] = 0
    ctx['small_cnt'] = 0
    for d in data[:20]:
        for x in [d[1],d[2],d[3]]:
            if x >= 5: ctx['big_cnt'] += 1
            else: ctx['small_cnt'] += 1
    
    # === 9. 重号统计 (理论: 27.1%) ===
    ctx['repeat_rate'] = 0
    repeat_total = 0
    for i in range(min(20, n-1)):
        curr = data[i]
        prev = data[i+1]
        for pos in range(3):
            repeat_total += 1
            if curr[pos+1] == prev[pos+1]:
                ctx['repeat_rate'] += 1
    ctx['repeat_rate'] = ctx['repeat_rate'] / max(repeat_total, 1)
    
    # === 10. Markov链转移概率 ===
    ctx['markov'] = [Counter(), Counter(), Counter()]
    for i in range(min(50, n-1)):
        for pos in range(3):
            prev_digit = data[i+1][pos+1]
            curr_digit = data[i][pos+1]
            ctx['markov'][pos][(prev_digit, curr_digit)] += 1
    
    # === 11. 形态统计 (理论: 豹子1%, 组三27%, 组六72%) ===
    ctx['shape'] = Counter()
    for d in data[:50]:
        unique = len(set([d[1], d[2], d[3]]))
        if unique == 1: ctx['shape']['baozi'] += 1
        elif unique == 2: ctx['shape']['zusan'] += 1
        else: ctx['shape']['zuliu'] += 1
    
    # === 12. 复隔中分析 (v5新增，参考中彩网专业分析师) ===
    if len(data) >= 3:
        last_draw = set([data[0][1], data[0][2], data[0][3]])  # 上期号码
        prev_draw = set([data[1][1], data[1][2], data[1][3]])  # 前两期号码
        
        # 复码：上期出现的数字
        fu = last_draw
        
        # 隔码：前两期出现但上期未出的数字
        ge = prev_draw - fu
        
        # 中码：其余数字（0-9去掉复码和隔码）
        all_digits = set(range(10))
        zhong = all_digits - fu - ge
        
        ctx['fugezhong'] = {
            'fu': fu,      # 复码
            'ge': ge,      # 隔码
            'zhong': zhong # 中码
        }
    
    # === 13. 和值5维分析 (v5新增，参考中彩网囚牛分析师) ===
    if len(data) >= 10:
        hz_list = [d[1]+d[2]+d[3] for d in data[:10]]
        
        # 和值奇偶
        hz_odd = sum(1 for h in hz_list if h % 2 == 1)
        hz_even = 10 - hz_odd
        target_parity = 1 if hz_odd > hz_even else 0
        
        # 和值大小 (0-13小，14-27大)
        hz_small = sum(1 for h in hz_list if h <= 13)
        hz_big = 10 - hz_small
        target_size = 1 if hz_big > hz_small else 0
        
        # 和值质合
        prime_hz = [2,3,5,7,11,13,17,19,23]
        hz_prime = sum(1 for h in hz_list if h in prime_hz)
        hz_composite = 10 - hz_prime
        target_prime = 1 if hz_prime > hz_composite else 0
        
        # 和值012路
        hz_roads = [0, 0, 0]
        for h in hz_list:
            hz_roads[h % 3] += 1
        target_road = hz_roads.index(max(hz_roads))
        
        # 和值尾
        hz_tails = [h % 10 for h in hz_list]
        
        # 和值振幅
        hz_amplitudes = [abs(hz_list[i] - hz_list[i+1]) for i in range(len(hz_list)-1)]
        
        # 目标和值范围
        avg_hz = sum(hz_list) / len(hz_list)
        std_hz = (sum((h - avg_hz)**2 for h in hz_list) / len(hz_list)) ** 0.5
        target_range = (max(0, int(avg_hz - std_hz)), min(27, int(avg_hz + std_hz)))
        
        ctx['hz5d'] = {
            'target_parity': target_parity,
            'target_size': target_size,
            'target_prime': target_prime,
            'target_road': target_road,
            'target_range': target_range,
            'hz_tails': hz_tails,
            'hz_amplitudes': hz_amplitudes
        }
    
    # === 14. 跨度5维分析 (v5新增，参考中彩网老K分析师) ===
    if len(data) >= 10:
        kd_list = [max(d[1],d[2],d[3]) - min(d[1],d[2],d[3]) for d in data[:10]]
        
        # 跨度质合
        prime_kd = [1,2,3,5,7]
        kd_prime = sum(1 for k in kd_list if k in prime_kd)
        kd_composite = 10 - kd_prime
        target_prime = 1 if kd_prime > kd_composite else 0
        
        # 跨度奇偶
        kd_odd = sum(1 for k in kd_list if k % 2 == 1)
        kd_even = 10 - kd_odd
        target_parity = 1 if kd_odd > kd_even else 0
        
        # 跨度大小 (0-4小，5-9大)
        kd_small = sum(1 for k in kd_list if k <= 4)
        kd_big = 10 - kd_small
        target_size = 1 if kd_big > kd_small else 0
        
        # 跨度振幅
        kd_amplitudes = [abs(kd_list[i] - kd_list[i+1]) for i in range(len(kd_list)-1)]
        
        # 跨度012路
        kd_roads = [0, 0, 0]
        for k in kd_list:
            kd_roads[k % 3] += 1
        
        ctx['kd5d'] = {
            'target_prime': target_prime,
            'target_parity': target_parity,
            'target_size': target_size,
            'kd_amplitudes': kd_amplitudes,
            'kd_roads': kd_roads
        }
    
    # === 15. 区段分布 (v5新增) ===
    if len(data) >= 10:
        # 小号区(0-2)、中号区(3-6)、大号区(7-9)
        small_count = 0
        mid_count = 0
        large_count = 0
        for d in data[:10]:
            for x in [d[1], d[2], d[3]]:
                if x <= 2: small_count += 1
                elif x <= 6: mid_count += 1
                else: large_count += 1
        
        # 目标区段分布（取众数）
        total = small_count + mid_count + large_count
        target_small = round(small_count / total * 3)
        target_mid = round(mid_count / total * 3)
        target_large = 3 - target_small - target_mid
        
        ctx['quduan'] = {
            'target_small': target_small,
            'target_mid': target_mid,
            'target_large': target_large
        }
    
    # === 16. 卡方检验 (v5新增) ===
    # 检验各位数字分布是否均匀
    chi2_stats = []
    for pos in range(3):
        observed = [ctx['freq100'][pos].get(d, 0) for d in range(10)]
        expected = sum(observed) / 10
        chi2 = sum((o - expected)**2 / expected for o in observed)
        chi2_stats.append(chi2)
    ctx['chi2'] = chi2_stats
    
    return ctx
```

## 评分公式 v5（整合专业分析师维度）

```python
def score_bet(b, s, g, ctx):
    """Score a 3-digit combination. Higher = better candidate.
    
    v5改进：整合专业分析师维度（复隔中、和值5维、跨度5维）
    """
    score = 0.0
    
    # ── 1. 和值合理性 (权重: 0.25) ── 和值7-20占83.2%
    hz = b + s + g
    hz_diff = abs(hz - ctx['hz_avg'])
    if hz_diff <= 2: score += 20
    elif hz_diff <= 4: score += 12
    elif hz_diff <= 6: score += 5
    if 7 <= hz <= 20: score += 8  # 高频区83.2%
    
    # ── 2. 跨度合理性 (权重: 0.20) ── 跨度4-7最常见
    kd = max(b, s, g) - min(b, s, g)
    score += ctx['kd_freq'].get(kd, 0) * 1.0
    if 4 <= kd <= 7: score += 5
    
    # ── 3. 组选形态 (权重: 0.15) ── 强制均衡
    unique = len(set([b, s, g]))
    if unique == 3: score += 8   # 组六最常见(72%)
    elif unique == 2: score += 4  # 组三(27%)
    # 豹子不加分(1%)
    
    # ── 4. 奇偶平衡 (权重: 0.10) ──
    odd_count = sum(1 for x in [b,s,g] if x % 2 == 1)
    if odd_count in [1, 2]: score += 5
    
    # ── 5. 大小平衡 (权重: 0.10) ──
    big_count = sum(1 for x in [b,s,g] if x >= 5)
    if big_count in [1, 2]: score += 5
    
    # ── 6. 位置频率 (权重: 0.08) ──
    score += ctx['freq20'][0].get(b, 0) * 1.0
    score += ctx['freq20'][1].get(s, 0) * 1.0
    score += ctx['freq20'][2].get(g, 0) * 1.0
    
    # ── 7. 加权热度 (权重: 0.05) ──
    heat = ctx['weighted'].get(b,0) + ctx['weighted'].get(s,0) + ctx['weighted'].get(g,0)
    score += heat * 0.05
    
    # ── 8. 012路匹配 (权重: 0.04) ──
    def road(x): return x % 3
    for pos, digit in enumerate([b, s, g]):
        r = road(digit)
        score += ctx['road20'][pos].get(r, 0) * 0.5
    
    # ── 9. 连号加分 (权重: 0.03) ──
    digits = sorted([b, s, g])
    for i in range(len(digits)-1):
        if digits[i+1] - digits[i] == 1:
            score += 3
            break
    
    # ── 10. 遗漏回补 (权重: 0.02) ── 仅作参考，不作为主要加分项
    # 仅考虑≥30期的极端遗漏(P=4.2%)
    for pos, digit in enumerate([b, s, g]):
        m = ctx['miss'][pos].get(digit, 0)
        if m >= 30:    # P=4.2%，罕见
            score += 2
    
    # ── 11. 近期重复惩罚 (保留) ──
    for d in ctx.get('recent5', []):
        if (b,s,g) == (d[1],d[2],d[3]):
            score -= 10
            break
    for d in ctx.get('recent10', []):
        if (b,s,g) == (d[1],d[2],d[3]):
            score -= 15
            break
    
    # ── 12. 专业维度加分 (v5新增) ──
    # 12.1 复隔中分析加分
    if 'fugezhong' in ctx:
        fgz = ctx['fugezhong']
        # 复码加分（上期出现的数字）
        if b in fgz['fu'] or s in fgz['fu'] or g in fgz['fu']:
            score += 3
        # 中码加分（既不是复码也不是隔码）
        mid_count = sum(1 for x in [b,s,g] if x in fgz['zhong'])
        if mid_count >= 2:
            score += 2
    
    # 12.2 和值5维分析加分
    if 'hz5d' in ctx:
        hz5d = ctx['hz5d']
        # 和值奇偶匹配
        if hz % 2 == hz5d['target_parity']:
            score += 2
        # 和值大小匹配
        if (hz >= 14) == hz5d['target_size']:
            score += 2
        # 和值质合匹配
        if (hz in [2,3,5,7,11,13,17,19,23]) == hz5d['target_prime']:
            score += 1
        # 和值012路匹配
        if hz % 3 == hz5d['target_road']:
            score += 1
    
    # 12.3 跨度5维分析加分
    if 'kd5d' in ctx:
        kd5d = ctx['kd5d']
        # 跨度质合匹配
        if (kd in [1,2,3,5,7]) == kd5d['target_prime']:
            score += 1
        # 跨度奇偶匹配
        if kd % 2 == kd5d['target_parity']:
            score += 1
        # 跨度大小匹配
        if (kd >= 5) == kd5d['target_size']:
            score += 1
    
    # 12.4 区段分布加分
    if 'quduan' in ctx:
        qd = ctx['quduan']
        small = sum(1 for x in [b,s,g] if x <= 2)
        mid = sum(1 for x in [b,s,g] if 3 <= x <= 6)
        large = sum(1 for x in [b,s,g] if x >= 7)
        # 匹配目标区段分布
        if small == qd['target_small'] and mid == qd['target_mid'] and large == qd['target_large']:
            score += 3
    
    return score
```

## 候选生成策略 (12种独立策略，v5新增3种专业维度策略)

```python
def generate_candidates(ctx, data):
    """Generate diverse candidates from 12 independent strategies.
    
    v5改进：新增3种专业维度策略（复隔中、和值5维、跨度5维）
    """
    import random
    candidates = set()
    
    # ── 策略1: 位置热号组合 ──
    top_bai = [x[0] for x in ctx['freq20'][0].most_common(6)]
    top_shi = [x[0] for x in ctx['freq20'][1].most_common(6)]
    top_ge = [x[0] for x in ctx['freq20'][2].most_common(6)]
    for b in top_bai:
        for s in top_shi:
            for g in top_ge:
                candidates.add((b, s, g))
    
    # ── 策略2: 加权热度组合 ──
    top7 = [x[0] for x in ctx['weighted'].most_common(7)]
    for b in top7:
        for s in top7:
            for g in top7:
                candidates.add((b, s, g))
    
    # ── 策略3: 和值目标组合 ──
    target_hz = int(ctx['hz_avg'])
    for b in range(10):
        for s in range(10):
            for g in range(10):
                if abs(b+s+g - target_hz) <= 3:
                    candidates.add((b, s, g))
    
    # ── 策略4: 组六优先组合 ──
    for _ in range(50):
        b, s, g = random.randint(0,9), random.randint(0,9), random.randint(0,9)
        if len(set([b, s, g])) == 3:  # 组六
            if 7 <= b+s+g <= 20:  # 和值合理
                candidates.add((b, s, g))
    
    # ── 策略5: 组三候选 ──
    zusan_recent = sum(1 for d in data[:5]
                       if len(set([d[1], d[2], d[3]])) == 2)
    if zusan_recent == 0:  # 组三"逾期"
        for d1 in top7[:5]:
            for d2 in top7[:5]:
                if d1 != d2:
                    candidates.add((d1, d1, d2))
                    candidates.add((d1, d2, d1))
                    candidates.add((d2, d1, d1))
    
    # ── 策略6: 012路组合 ──
    def road(x): return x % 3
    for pos in range(3):
        hot_roads = [r for r, _ in ctx['road20'][pos].most_common(2)]
        hot_digits = [d for d in range(10) if road(d) in hot_roads]
        for d in hot_digits[:4]:
            for h in top7:
                for h2 in top7:
                    combo = [h, h2, h2]
                    combo[pos] = d
                    candidates.add(tuple(combo))
    
    # ── 策略7: 遗漏回补组合 (仅极端遗漏) ──
    # 只考虑≥30期的极端遗漏(P=4.2%)
    for pos in range(3):
        high_miss = sorted(ctx['miss'][pos].items(), key=lambda x: -x[1])
        high_miss = [(d, m) for d, m in high_miss if m >= 30][:2]
        for d, _ in high_miss:
            for h in top7:
                for h2 in top7:
                    combo = [h, h2, h2]
                    combo[pos] = d
                    candidates.add(tuple(combo))
    
    # ── 策略8: Markov转移候选 ──
    if data and len(data) >= 2:
        last = data[0]
        for pos in range(3):
            prev_digit = last[pos+1]
            trans_counts = Counter()
            for i in range(min(50, len(data)-1)):
                if data[i+1][pos+1] == prev_digit:
                    trans_counts[data[i][pos+1]] += 1
            top_trans = [d for d, _ in trans_counts.most_common(4)]
            for d in top_trans:
                for h in top7:
                    for h2 in top7:
                        combo = [h, h2, h2]
                        combo[pos] = d
                        candidates.add(tuple(combo))
    
    # ── 策略9: 纯随机组合 ──
    for _ in range(30):
        b, s, g = random.randint(0,9), random.randint(0,9), random.randint(0,9)
        candidates.add((b, s, g))
    
    # ── 策略10: 复隔中组合 (v5新增) ──
    if 'fugezhong' in ctx:
        fgz = ctx['fugezhong']
        # 复码+中码组合
        fu_digits = list(fgz['fu'])
        zhong_digits = list(fgz['zhong'])
        for f in fu_digits[:3]:
            for z1 in zhong_digits[:4]:
                for z2 in zhong_digits[:4]:
                    candidates.add((f, z1, z2))
                    candidates.add((z1, f, z2))
                    candidates.add((z1, z2, f))
        # 中码主导组合
        for z1 in zhong_digits[:5]:
            for z2 in zhong_digits[:5]:
                for z3 in zhong_digits[:5]:
                    candidates.add((z1, z2, z3))
    
    # ── 策略11: 和值5维组合 (v5新增) ──
    if 'hz5d' in ctx:
        hz5d = ctx['hz5d']
        # 根据和值5维分析生成候选
        target_hz_range = hz5d['target_range']  # (min_hz, max_hz)
        for b in range(10):
            for s in range(10):
                for g in range(10):
                    hz = b + s + g
                    if target_hz_range[0] <= hz <= target_hz_range[1]:
                        # 检查奇偶、大小、质合、012路
                        hz_parity = hz % 2
                        hz_size = 1 if hz >= 14 else 0
                        hz_prime = 1 if hz in [2,3,5,7,11,13,17,19,23] else 0
                        hz_road = hz % 3
                        
                        if (hz_parity == hz5d['target_parity'] and
                            hz_size == hz5d['target_size'] and
                            hz_prime == hz5d['target_prime'] and
                            hz_road == hz5d['target_road']):
                            candidates.add((b, s, g))
    
    # ── 策略12: 跨度5维组合 (v5新增) ──
    if 'kd5d' in ctx:
        kd5d = ctx['kd5d']
        # 根据跨度5维分析生成候选
        for b in range(10):
            for s in range(10):
                for g in range(10):
                    kd = max(b, s, g) - min(b, s, g)
                    # 检查跨度质合、奇偶、大小
                    kd_prime = 1 if kd in [1,2,3,5,7] else 0
                    kd_parity = kd % 2
                    kd_size = 1 if kd >= 5 else 0
                    
                    if (kd_prime == kd5d['target_prime'] and
                        kd_parity == kd5d['target_parity'] and
                        kd_size == kd5d['target_size']):
                        candidates.add((b, s, g))
    
    return candidates
```

## 完整执行流程

```python
def analyze_and_recommend(data, top_n=10):
    """Complete analysis pipeline."""
    ctx = compute_context(data)
    ctx['recent5'] = data[:5]
    ctx['recent10'] = data[:10]
    ctx['last_draw'] = data[0] if data else None
    
    candidates = generate_candidates(ctx, data)
    
    scored = []
    for b, s, g in candidates:
        sc = score_bet(b, s, g, ctx)
        hz = b + s + g
        kd = max(b,s,g) - min(b,s,g)
        scored.append((sc, b, s, g, hz, kd))
    
    scored.sort(key=lambda x: -x[0])
    return scored[:top_n]
```

## 关于"遗漏回补"的数学说明

**赌徒谬误 (Gambler's Fallacy)**: 认为"某号码很久没出了，下次更可能出现"是错误的。
每期开奖是独立事件，概率不变。但作为用户要求的分析维度，我们用以下框架：

- **遗漏≥15期** (P=20.6%): 值得关注，但不是"必出"信号
- **遗漏≥20期** (P=12.2%): 较少见，可作为参考
- **遗漏≥30期** (P=4.2%): 罕见，但仍有4.2%概率发生

**为什么不排除近期号码?**
- 重号概率: 27.1%（每3.7期约出现一次）
- 硬排除会导致错过这些有概率出现的组合
- 改用加权惩罚(-15/-25分)更合理

## 输出模板

参照 `templates/output_format.md`，极简风格，只展示推荐结果。
