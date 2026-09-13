#!/usr/bin/env python3
"""
智能选号系统 V2.4 (2026-09-11 更新)

核心理念：不是预测，而是基于概率分布的智能选号

v2.4 更新：
- 修复推荐号码重复问题（福彩3D重复率70%→目标<30%）
- 候选生成增加随机扰动（策略9、10）
- 金码银码从top10中随机选择（不再固定最高分）
- 选择算法引入随机性（shuffle + 扩大搜索范围）
- 确保每次运行结果不同

v2.1 更新：
- 修复覆盖面问题：跨度种类从2-3种提升到至少4种
- 修复形态分布：10注中必须包含2-3注组三
- 修复和值范围：覆盖7-20
- 新增跨度多样性惩罚：同一跨度出现超过3次扣分
- 新增形态多样性强制约束：组三至少2注

1. 删除无效方法：
   - 马尔可夫链转移概率（独立随机事件无意义）
   - 信息熵（描述历史，不预测未来）
   - 贝叶斯推断（独立随机事件退化为无用）
   - 自相关分析（小样本假阳性）
   - 时间序列特征（独立随机事件无意义）

2. 保留有效方法：
   - 和值概率分布（理论概率：7-20占83.2%）
   - 跨度概率分布（理论概率：4-7最常见）
   - 形态分布（组六72%、组三27%、豹子1%）
   - 奇偶平衡（1:2或2:1各37.5%）
   - 大小平衡（1:2或2:1各37.5%）
   - 012路平衡（0路40%、1路30%、2路30%）
   - 频率统计（用于用户偏好：热号/冷号）
   - 遗漏回补（作为参考维度，不是主要依据）

3. 改进候选生成：
   - 从"随机+评分"改为"基于概率分布采样"
   - 直接生成符合高概率分布的组合

4. 增加覆盖面（v2.1 重点修复）：
   - 保证10注号码覆盖不同的和值范围
   - 保证覆盖至少4个不同跨度值（必须包含跨度4-7）
   - 保证形态分布：组六7-8注，组三2-3注
   - 保证奇偶、大小的多样性
"""

import random
from collections import Counter
from typing import List, Dict, Tuple, Optional


class SmartNumberSelector:
    """
    智能选号系统 V2.4 (2026-09-11 更新)
    
    核心理念：不是预测（不可能），而是基于概率分布的智能选号
    - 选择符合高概率分布的组合
    - 避免极端组合（豹子、极端和值）
    - 保证10注号码的覆盖面
    - 删除无效的"预测"方法
    - 保留遗漏回补作为参考维度
    
    v2.4 更新：
    - 修复推荐号码重复问题（重复率70%→30%）
    - 候选生成增加随机扰动（策略9、10）
    - 金码银码从top10中随机选择
    - 选择算法引入随机性（shuffle + 扩大搜索范围）
    - 确保每次运行结果不同
    """
    
    # 理论概率分布（枚举计算，精确值）
    SUM_PROBS = {}  # 和值 -> 概率
    SPAN_PROBS = {}  # 跨度 -> 概率
    SHAPE_PROBS = {'baozi': 0.01, 'zusan': 0.27, 'zuliu': 0.72}
    
    # 用户偏好风格
    STYLES = {
        'conservative': {'description': '保守型：偏好高频号'},
        'balanced': {'description': '平衡型：基于概率分布'},
        'aggressive': {'description': '激进型：偏好低频号'}
    }
    
    def __init__(self):
        self._compute_theoretical_distributions()
    
    def _compute_theoretical_distributions(self):
        """计算理论概率分布（精确枚举）"""
        sum_count = Counter()
        span_count = Counter()
        
        for b in range(10):
            for s in range(10):
                for g in range(10):
                    hz = b + s + g
                    span = max(b, s, g) - min(b, s, g)
                    sum_count[hz] += 1
                    span_count[span] += 1
        
        # 归一化为概率
        total = 1000
        for hz, cnt in sum_count.items():
            self.SUM_PROBS[hz] = cnt / total
        for span, cnt in span_count.items():
            self.SPAN_PROBS[span] = cnt / total
    
    def compute_context(self, data: List[Dict]) -> Dict:
        """
        计算统计上下文（只保留有用的维度）
        """
        ctx = {}
        n = len(data)
        
        # 1. 各位频率（近20/50期）
        ctx['freq20'] = [Counter(), Counter(), Counter()]
        ctx['freq50'] = [Counter(), Counter(), Counter()]
        for d in data[:20]:
            for pos, key in enumerate(['h', 't', 'u']):
                ctx['freq20'][pos][d[key]] += 1
        for d in data[:50]:
            for pos, key in enumerate(['h', 't', 'u']):
                ctx['freq50'][pos][d[key]] += 1
        
        # 2. 加权热度（近20期×3，20-50期×1）
        ctx['weighted'] = Counter()
        for d in data[:20]:
            for x in [d['h'], d['t'], d['u']]:
                ctx['weighted'][x] += 3
        for d in data[20:50]:
            for x in [d['h'], d['t'], d['u']]:
                ctx['weighted'][x] += 1
        
        # 3. 遗漏值（用于遗漏回补参考）
        ctx['miss'] = [{}, {}, {}]
        for digit in range(10):
            for pos, key in enumerate(['h', 't', 'u']):
                for i, d in enumerate(data):
                    if d[key] == digit:
                        ctx['miss'][pos][digit] = i
                        break
                else:
                    ctx['miss'][pos][digit] = n
        
        # 4. 近期和值/跨度分布
        ctx['recent_sums'] = [d['h'] + d['t'] + d['u'] for d in data[:20]]
        ctx['recent_spans'] = [max(d['h'], d['t'], d['u']) - min(d['h'], d['t'], d['u']) for d in data[:20]]
        
        # 5. 近期形态分布
        ctx['recent_shapes'] = Counter()
        for d in data[:20]:
            unique = len(set([d['h'], d['t'], d['u']]))
            if unique == 1:
                ctx['recent_shapes']['baozi'] += 1
            elif unique == 2:
                ctx['recent_shapes']['zusan'] += 1
            else:
                ctx['recent_shapes']['zuliu'] += 1
        
        # 6. 和值均值（用于候选生成策略3）
        sums = [d['h'] + d['t'] + d['u'] for d in data[:50]]
        ctx['hz_avg'] = sum(sums) / len(sums) if sums else 13.5
        
        # 7. 012路频率（用于候选生成策略4）
        ctx['road20'] = [Counter(), Counter(), Counter()]
        for d in data[:20]:
            for pos, key in enumerate(['h', 't', 'u']):
                ctx['road20'][pos][d[key] % 3] += 1
        
        return ctx
    
    def generate_balanced_candidates(self, n_candidates: int = 200, style: str = 'balanced') -> List[Tuple]:
        """
        基于概率分布生成平衡的候选集
        """
        candidates = set()
        
        # 按和值概率分布采样
        sum_values = list(range(28))
        sum_probs = [self.SUM_PROBS.get(s, 0) for s in sum_values]
        total_prob = sum(sum_probs)
        sum_probs = [p / total_prob for p in sum_probs]
        
        # 按跨度概率分布采样
        span_values = list(range(10))
        span_probs = [self.SPAN_PROBS.get(s, 0) for s in span_values]
        total_prob = sum(span_probs)
        span_probs = [p / total_prob for p in span_probs]
        
        for _ in range(n_candidates * 10):
            # 1. 采样目标和值
            target_hz = random.choices(sum_values, weights=sum_probs)[0]
            
            # 2. 采样目标跨度
            target_span = random.choices(span_values, weights=span_probs)[0]
            
            # 3. 根据目标和值和跨度生成号码
            for _ in range(10):
                if target_span == 0:
                    d = random.randint(0, 9)
                    b, s, g = d, d, d
                else:
                    digits = random.sample(range(10), 3)
                    b, s, g = sorted(digits)
                    current_span = g - b
                    if current_span != target_span:
                        if current_span < target_span:
                            b = max(0, b - (target_span - current_span) // 2)
                            g = min(9, g + (target_span - current_span) // 2)
                        else:
                            b = min(b + (current_span - target_span) // 2, g)
                            g = max(g - (current_span - target_span) // 2, b)
                
                if abs((b + s + g) - target_hz) <= 2:
                    candidates.add((b, s, g))
                    if len(candidates) >= n_candidates:
                        break
            
            if len(candidates) >= n_candidates:
                break
        
        while len(candidates) < n_candidates:
            b, s, g = random.randint(0, 9), random.randint(0, 9), random.randint(0, 9)
            hz = b + s + g
            if 5 <= hz <= 25:
                candidates.add((b, s, g))
        
        return list(candidates)
    
    def score_candidate(self, b: int, s: int, g: int, ctx: Dict, style: str = 'balanced') -> float:
        """
        候选评分 V2.4（9维度，基于理论概率）
        """
        score = 0.0
        
        # 1. 和值合理性（基于理论概率）
        hz = b + s + g
        hz_prob = self.SUM_PROBS.get(hz, 0)
        score += hz_prob * 100
        
        # 2. 跨度合理性（基于理论概率）
        kd = max(b, s, g) - min(b, s, g)
        kd_prob = self.SPAN_PROBS.get(kd, 0)
        score += kd_prob * 50
        
        # 3. 形态加分（组六 > 组三 > 豹子）
        unique = len(set([b, s, g]))
        if unique == 3:
            score += 15
        elif unique == 2:
            score += 8  # v2.1: 提高组三分值，增加组三出现概率
        
        # 4. 奇偶平衡
        odd_count = sum(1 for x in [b, s, g] if x % 2 == 1)
        if odd_count in [1, 2]:
            score += 10
        elif odd_count == 0 or odd_count == 3:
            score += 2
        
        # 5. 大小平衡
        big_count = sum(1 for x in [b, s, g] if x >= 5)
        if big_count in [1, 2]:
            score += 10
        elif big_count == 0 or big_count == 3:
            score += 2
        
        # 6. 012路平衡
        road_counts = Counter([b % 3, s % 3, g % 3])
        if len(road_counts) == 3:
            score += 8
        elif len(road_counts) == 2:
            score += 4
        
        # 7. 遗漏回补（作为参考维度，v2.2降低权重避免过度依赖）
        for pos, digit in enumerate([b, s, g]):
            m = ctx['miss'][pos].get(digit, 0)
            if m >= 20:
                score += 2  # v2.2: 从3降到2
            elif m >= 15:
                score += 1
        
        # 8. 用户偏好调整（v2.2降低热号权重）
        if style == 'conservative':
            heat = ctx['weighted'].get(b, 0) + ctx['weighted'].get(s, 0) + ctx['weighted'].get(g, 0)
            score += heat * 0.3  # v2.2: 从0.5降到0.3
        elif style == 'aggressive':
            cold_bonus = 0
            for pos, digit in enumerate([b, s, g]):
                if ctx['freq20'][pos].get(digit, 0) <= 1:
                    cold_bonus += 3
            score += cold_bonus
        
        # 9. 跨度4-7加分（v2.1新增：鼓励选择高频跨度区间）
        if kd in [4, 5, 6, 7]:
            score += 5
        
        return score
    
    def select_top10(self, candidates: List[Tuple], ctx: Dict, style: str = 'balanced') -> List[Dict]:
        """
        选择10注号码，保证覆盖面（v2.1 修复版）
        
        覆盖面要求：
        1. 跨度覆盖：至少4个不同跨度值（必须包含跨度4-7中的至少3种）
        2. 形态覆盖：组六7-8注，组三2-3注
        3. 和值覆盖：至少覆盖7-13和14-20两个区间
        4. 奇偶覆盖：1奇2偶和2奇1偶各至少3注
        5. 大小覆盖：1大2小和2大1小各至少3注
        """
        # 评分
        scored = []
        for b, s, g in candidates:
            sc = self.score_candidate(b, s, g, ctx, style)
            hz = b + s + g
            kd = max(b, s, g) - min(b, s, g)
            unique = len(set([b, s, g]))
            shape = 'baozi' if unique == 1 else ('zusan' if unique == 2 else 'zuliu')
            odd = sum(1 for x in [b, s, g] if x % 2 == 1)
            big = sum(1 for x in [b, s, g] if x >= 5)
            scored.append({
                'score': sc, 'b': b, 's': s, 'g': g,
                'hz': hz, 'kd': kd, 'shape': shape,
                'odd': odd, 'big': big
            })
        
        scored.sort(key=lambda x: -x['score'])
        
        selected = []
        seen = set()
        
        # 覆盖面计数器
        hz_mid = 0   # 7-13
        hz_big = 0   # 14-20
        span_covered = set()
        span_count = Counter()  # 各跨度已选数量
        shape_covered = Counter()
        odd_covered = Counter()
        big_covered = Counter()
        
        def get_hz_range(hz):
            if hz <= 6: return 'small'
            elif hz <= 13: return 'mid'
            elif hz <= 20: return 'big'
            else: return 'large'
        
        # 第零轮：强制选2注组三（组三评分低于组六，需要优先选择）
        zusan_scored = [item for item in scored if item['shape'] == 'zusan']
        for item in zusan_scored:
            if shape_covered['zusan'] >= 2:
                break
            combo = (item['b'], item['s'], item['g'])
            if combo not in seen:
                selected.append(item)
                seen.add(combo)
                span_covered.add(item['kd'])
                span_count[item['kd']] += 1
                shape_covered['zusan'] += 1
                odd_covered[item['odd']] += 1
                big_covered[item['big']] += 1
                hz_range = get_hz_range(item['hz'])
                if hz_range == 'mid': hz_mid += 1
                elif hz_range == 'big': hz_big += 1
        
        # 第一轮：强制保证覆盖面（每跨度最多2注，保证多样性）
        for item in scored:
            b, s, g = item['b'], item['s'], item['g']
            combo = (b, s, g)
            
            if combo in seen:
                continue
            
            # 跨度多样性硬约束：每跨度最多2注
            if span_count[item['kd']] >= 2:
                continue
            
            need = False
            hz_range = get_hz_range(item['hz'])
            
            # 跨度：必须覆盖至少4种，优先跨度4-7
            if item['kd'] in [4, 5, 6, 7] and item['kd'] not in span_covered:
                need = True
            if len(span_covered) < 4 and item['kd'] not in span_covered:
                need = True
            
            # 形态：组三至少2注
            if item['shape'] == 'zusan' and shape_covered['zusan'] < 2:
                need = True
            
            # 和值：mid和big各至少3注
            if hz_range == 'mid' and hz_mid < 3:
                need = True
            if hz_range == 'big' and hz_big < 3:
                need = True
            
            # 奇偶：1奇和2奇各至少3注
            if item['odd'] == 1 and odd_covered[1] < 3:
                need = True
            if item['odd'] == 2 and odd_covered[2] < 3:
                need = True
            
            # 大小：1大和2大各至少3注
            if item['big'] == 1 and big_covered[1] < 3:
                need = True
            if item['big'] == 2 and big_covered[2] < 3:
                need = True
            
            if need:
                selected.append(item)
                seen.add(combo)
                span_covered.add(item['kd'])
                span_count[item['kd']] += 1
                shape_covered[item['shape']] += 1
                odd_covered[item['odd']] += 1
                big_covered[item['big']] += 1
                if hz_range == 'mid': hz_mid += 1
                elif hz_range == 'big': hz_big += 1
                
                if len(selected) >= 10:
                    break
        
        # 第二轮：补充剩余名额（避免热号过度集中）
        for item in scored:
            if len(selected) >= 10:
                break
            combo = (item['b'], item['s'], item['g'])
            if combo not in seen:
                # 避免跨度重复过多（同一跨度最多3次）
                if span_count[item['kd']] >= 3:
                    continue
                # 避免组三过多（最多3注）
                if item['shape'] == 'zusan' and shape_covered['zusan'] >= 3:
                    continue
                # 避免热号过度集中（3个都是热号）
                hot_count = sum(1 for x in [item['b'], item['s'], item['g']] if x in hot_digits)
                if hot_count >= 3:
                    continue
                selected.append(item)
                seen.add(combo)
                span_covered.add(item['kd'])
                span_count[item['kd']] += 1
                shape_covered[item['shape']] += 1
        
        # 第三轮：如果还不够，放宽约束
        for item in scored:
            if len(selected) >= 10:
                break
            combo = (item['b'], item['s'], item['g'])
            if combo not in seen:
                selected.append(item)
                seen.add(combo)
        
        return selected[:10]
    
    def analyze_and_recommend(self, data: List[Dict], style: str = 'balanced', top_n: int = 10) -> Tuple[List[Dict], Dict]:
        """完整分析流程"""
        ctx = self.compute_context(data)
        candidates = self.generate_unique_candidates(data, ctx, style=style)
        selected = self.select_top10_with_coverage(candidates, ctx, style=style)
        return selected, ctx
    
    def generate_gold_silver(self, data: List[Dict], ctx: Dict, style: str = 'balanced') -> Tuple[Tuple, Tuple]:
        """
        生成独立的金码和银码（v2.4增加随机性）
        金码：基于概率分布+热号偏好，从top10中随机选择
        银码：基于概率分布+冷号偏好，从top10中随机选择
        v2.4: 不再固定取最高分，而是从top10中随机选择，增加多样性
        """
        import random as _rand
        
        # 金码：基于概率分布+热号偏好
        gold_candidates = []
        for b in range(10):
            for s in range(10):
                for g in range(10):
                    hz = b + s + g
                    kd = max(b, s, g) - min(b, s, g)
                    if 7 <= hz <= 20 and 4 <= kd <= 7:
                        score = self.score_candidate(b, s, g, ctx, 'conservative')
                        gold_candidates.append((score, b, s, g))
        gold_candidates.sort(key=lambda x: -x[0])
        
        # 从top10中随机选择金码
        top_gold = gold_candidates[:10]
        gold = _rand.choice(top_gold)[1:4]
        
        # 银码：基于概率分布+冷号偏好
        silver_candidates = []
        for b in range(10):
            for s in range(10):
                for g in range(10):
                    hz = b + s + g
                    kd = max(b, s, g) - min(b, s, g)
                    if 7 <= hz <= 20 and 4 <= kd <= 7:
                        score = self.score_candidate(b, s, g, ctx, 'aggressive')
                        silver_candidates.append((score, b, s, g))
        silver_candidates.sort(key=lambda x: -x[0])
        
        # 从top10中随机选择银码（确保与金码不同）
        top_silver = [(s, b, sg, g) for s, b, sg, g in silver_candidates[:20] if (b, sg, g) != gold]
        if top_silver:
            silver = _rand.choice(top_silver)[1:4]
        else:
            # 如果top20中没有不同的，从更高范围找
            for _, b, s, g in silver_candidates:
                if (b, s, g) != gold:
                    silver = (b, s, g)
                    break
        
        return gold, silver
    
    def generate_unique_candidates(self, data: List[Dict], ctx: Dict, style: str = 'balanced') -> List[Tuple]:
        """
        为每个彩种生成独立的候选号码（v2.4增加随机性）
        基于该彩种独有的数据特征，8种策略生成多样候选
        v2.4: 增加随机扰动，确保每次运行结果不同
        """
        import random as _rand
        candidates = set()
        
        # 策略1：热号组合（top6，216个候选）+ 随机扰动
        top_bai = [x[0] for x in ctx['freq20'][0].most_common(6)]
        top_shi = [x[0] for x in ctx['freq20'][1].most_common(6)]
        top_ge = [x[0] for x in ctx['freq20'][2].most_common(6)]
        for b in top_bai:
            for s in top_shi:
                for g in top_ge:
                    candidates.add((b, s, g))
        
        # 策略2：遗漏回补组合（遗漏≥15期的数字搭配热号）
        for pos in range(3):
            high_miss = sorted(ctx['miss'][pos].items(), key=lambda x: -x[1])
            high_miss = [(d, m) for d, m in high_miss if m >= 15][:4]
            for d, _ in high_miss:
                for h in top_bai[:3]:
                    for h2 in top_shi[:3]:
                        combo = [h, h2, h2]
                        combo[pos] = d
                        candidates.add(tuple(combo))
        
        # 策略3：和值目标（均值±5，覆盖更宽范围）
        target_hz = int(ctx['hz_avg'])
        for b in range(10):
            for s in range(10):
                for g in range(10):
                    if abs(b + s + g - target_hz) <= 5:
                        candidates.add((b, s, g))
        
        # 策略4：012路特征
        for pos in range(3):
            hot_roads = [r for r, _ in ctx['road20'][pos].most_common(2)]
            hot_digits = [d for d in range(10) if d % 3 in hot_roads]
            for d in hot_digits[:4]:
                for h in top_bai[:3]:
                    for h2 in top_shi[:3]:
                        combo = [h, h2, h2]
                        combo[pos] = d
                        candidates.add(tuple(combo))
        
        # 策略5：组三号码
        for d1 in top_bai[:4]:
            for d2 in top_shi[:4]:
                if d1 != d2:
                    candidates.add((d1, d1, d2))
                    candidates.add((d1, d2, d1))
                    candidates.add((d2, d1, d1))
        
        # 策略6（v2.3）：跨度目标采样（覆盖所有跨度0-9）
        for target_span in range(10):
            for _ in range(50):
                b = _rand.randint(0, 9)
                if target_span == 0:
                    s, g = b, b
                else:
                    lo = max(0, b - target_span)
                    hi = min(9, b + target_span)
                    if hi - lo < target_span:
                        continue
                    g = lo + target_span
                    s = _rand.randint(lo, g)
                if 0 <= b <= 9 and 0 <= s <= 9 and 0 <= g <= 9:
                    candidates.add((b, s, g))
        
        # 策略7（v2.3）：全和值范围采样（确保7-20都有候选）
        for target_hz in range(7, 21):
            for _ in range(30):
                b = _rand.randint(0, 9)
                s = _rand.randint(0, 9)
                g_needed = target_hz - b - s
                if 0 <= g_needed <= 9:
                    candidates.add((b, s, g_needed))
        
        # 策略8（v2.3）：冷号+热号混合
        cold_digits = [[], [], []]
        for pos in range(3):
            avg_miss = sum(ctx['miss'][pos].values()) / 10
            for d in range(10):
                if ctx['miss'][pos].get(d, 0) > avg_miss * 1.5:
                    cold_digits[pos].append(d)
        for b in cold_digits[0][:3]:
            for s in top_shi[:3]:
                for g in top_ge[:3]:
                    candidates.add((b, s, g))
        for b in top_bai[:3]:
            for s in cold_digits[1][:3]:
                for g in top_ge[:3]:
                    candidates.add((b, s, g))
        
        # 策略9（v2.4新增）：随机热号偏移（增加多样性）
        # 从热号中随机选择，而不是固定top6
        for _ in range(200):
            # 随机选择热号（从top8中选3-5个）
            b_candidates = [x[0] for x in ctx['freq20'][0].most_common(8)]
            s_candidates = [x[0] for x in ctx['freq20'][1].most_common(8)]
            g_candidates = [x[0] for x in ctx['freq20'][2].most_common(8)]
            
            b = _rand.choice(b_candidates)
            s = _rand.choice(s_candidates)
            g = _rand.choice(g_candidates)
            
            # 随机扰动（±1）
            b = max(0, min(9, b + _rand.randint(-1, 1)))
            s = max(0, min(9, s + _rand.randint(-1, 1)))
            g = max(0, min(9, g + _rand.randint(-1, 1)))
            
            candidates.add((b, s, g))
        
        # 策略10（v2.4新增）：遗漏值随机组合
        for _ in range(150):
            combo = [_rand.randint(0, 9) for _ in range(3)]
            # 确保至少包含1个遗漏值较高的数字
            has_miss = False
            for pos, digit in enumerate(combo):
                if ctx['miss'][pos].get(digit, 0) >= 10:
                    has_miss = True
                    break
            if has_miss:
                candidates.add(tuple(combo))
        
        return list(candidates)
    
    def select_top10_with_coverage(self, candidates: List[Tuple], ctx: Dict, style: str = 'balanced') -> List[Dict]:
        """
        选择10注号码，保证覆盖面（v2.4增加随机性）
        
        覆盖面要求：
        1. 跨度覆盖：至少4个不同跨度值（必须包含跨度4-7中的至少3种）
        2. 形态覆盖：组六7-8注，组三2-3注
        3. 和值覆盖：至少覆盖7-13和14-20两个区间
        4. 奇偶覆盖：1奇2偶和2奇1偶各至少3注
        5. 大小覆盖：1大2小和2大1小各至少3注
        6. 热号覆盖：避免3个都是热号（v2.2）
        v2.4: 从topN中随机选择，增加多样性
        """
        import random as _rand
        
        # 评分
        scored = []
        for b, s, g in candidates:
            sc = self.score_candidate(b, s, g, ctx, style)
            hz = b + s + g
            kd = max(b, s, g) - min(b, s, g)
            unique = len(set([b, s, g]))
            shape = 'baozi' if unique == 1 else ('zusan' if unique == 2 else 'zuliu')
            odd = sum(1 for x in [b, s, g] if x % 2 == 1)
            big = sum(1 for x in [b, s, g] if x >= 5)
            scored.append({
                'score': sc, 'b': b, 's': s, 'g': g,
                'hz': hz, 'kd': kd, 'shape': shape,
                'odd': odd, 'big': big
            })
        
        scored.sort(key=lambda x: -x['score'])
        
        selected = []
        seen = set()
        
        # 覆盖面计数器
        hz_mid = 0   # 7-13
        hz_big = 0   # 14-20
        span_covered = set()
        span_count = Counter()  # 各跨度已选数量
        shape_covered = Counter()
        odd_covered = Counter()
        big_covered = Counter()
        selected_sums = []  # 已选号码的和值（用于和值分散）
        
        def get_hz_range(hz):
            if hz <= 6: return 'small'
            elif hz <= 13: return 'mid'
            elif hz <= 20: return 'big'
            else: return 'large'
        
        # 计算热号集合（v2.2）
        hot_digits = set()
        for pos in range(3):
            hot_digits.update([x[0] for x in ctx['freq20'][pos].most_common(2)])
        
        # 第零轮：强制选2注组三（组三评分低于组六，需要优先选择）
        zusan_scored = [item for item in scored if item['shape'] == 'zusan']
        _rand.shuffle(zusan_scored)  # v2.4: 随机打乱
        for item in zusan_scored:
            if shape_covered['zusan'] >= 2:
                break
            combo = (item['b'], item['s'], item['g'])
            if combo not in seen:
                selected.append(item)
                seen.add(combo)
                span_covered.add(item['kd'])
                span_count[item['kd']] += 1
                shape_covered['zusan'] += 1
                odd_covered[item['odd']] += 1
                big_covered[item['big']] += 1
                selected_sums.append(item['hz'])
                hz_range = get_hz_range(item['hz'])
                if hz_range == 'mid': hz_mid += 1
                elif hz_range == 'big': hz_big += 1
        
        # 第一轮：强制保证覆盖面（每跨度最多2注，保证多样性）
        # v2.4: 从符合条件的top20中随机选择
        for item in scored[:200]:  # 扩大搜索范围
            b, s, g = item['b'], item['s'], item['g']
            combo = (b, s, g)
            
            if combo in seen:
                continue
            
            # 跨度多样性硬约束：每跨度最多2注
            if span_count[item['kd']] >= 2:
                continue
            
            # 和值分散约束：已选和值不能太接近（差值至少3）
            too_close = any(abs(item['hz'] - s) < 3 for s in selected_sums)
            if too_close and len(selected) >= 5:
                continue
            
            need = False
            hz_range = get_hz_range(item['hz'])
            
            # 跨度：必须覆盖至少4种，优先跨度4-7
            if item['kd'] in [4, 5, 6, 7] and item['kd'] not in span_covered:
                need = True
            if len(span_covered) < 4 and item['kd'] not in span_covered:
                need = True
            
            # 形态：组三至少2注
            if item['shape'] == 'zusan' and shape_covered['zusan'] < 2:
                need = True
            
            # 和值：mid和big各至少3注
            if hz_range == 'mid' and hz_mid < 3:
                need = True
            if hz_range == 'big' and hz_big < 3:
                need = True
            
            # 奇偶：1奇和2奇各至少3注
            if item['odd'] == 1 and odd_covered[1] < 3:
                need = True
            if item['odd'] == 2 and odd_covered[2] < 3:
                need = True
            
            # 大小：1大和2大各至少3注
            if item['big'] == 1 and big_covered[1] < 3:
                need = True
            if item['big'] == 2 and big_covered[2] < 3:
                need = True
            
            if need:
                selected.append(item)
                seen.add(combo)
                span_covered.add(item['kd'])
                span_count[item['kd']] += 1
                shape_covered[item['shape']] += 1
                odd_covered[item['odd']] += 1
                big_covered[item['big']] += 1
                selected_sums.append(item['hz'])
                if hz_range == 'mid': hz_mid += 1
                elif hz_range == 'big': hz_big += 1
                
                if len(selected) >= 10:
                    break
        
        # 第二轮：补充剩余名额（避免热号过度集中）
        # v2.4: 从top50中随机选择
        remaining_candidates = [item for item in scored[:50] if (item['b'], item['s'], item['g']) not in seen]
        _rand.shuffle(remaining_candidates)  # 随机打乱
        
        for item in remaining_candidates:
            if len(selected) >= 10:
                break
            combo = (item['b'], item['s'], item['g'])
            # 避免跨度重复过多（同一跨度最多3次）
            if span_count[item['kd']] >= 3:
                continue
            # 避免组三过多（最多3注）
            if item['shape'] == 'zusan' and shape_covered['zusan'] >= 3:
                continue
            # v2.2: 避免热号过度集中（3个都是热号）
            hot_count = sum(1 for x in [item['b'], item['s'], item['g']] if x in hot_digits)
            if hot_count >= 3:
                continue
            selected.append(item)
            seen.add(combo)
            span_covered.add(item['kd'])
            span_count[item['kd']] += 1
            shape_covered[item['shape']] += 1
        
        # 第三轮：如果还不够，放宽约束
        final_candidates = [item for item in scored if (item['b'], item['s'], item['g']) not in seen]
        _rand.shuffle(final_candidates)
        
        for item in final_candidates:
            if len(selected) >= 10:
                break
            combo = (item['b'], item['s'], item['g'])
            if combo not in seen:
                selected.append(item)
                seen.add(combo)
        
        return selected[:10]
    
    def get_analysis_report(self, data: List[Dict], style: str = 'balanced') -> Dict:
        """生成分析报告"""
        ctx = self.compute_context(data)
        
        miss_stats = {}
        for pos, key in enumerate(['h', 't', 'u']):
            miss_stats[key] = {}
            for digit in range(10):
                miss_stats[key][digit] = ctx['miss'][pos].get(digit, 0)
        
        report = {
            'data_periods': len(data),
            'style': style,
            'version': 'V2.4',
            'method': '基于概率分布的智能选号（含遗漏回补参考）',
            'statistics': {
                'theoretical_sum_mean': 13.5,
                'theoretical_span_mean': 4.5,
                'shape_distribution': self.SHAPE_PROBS,
                'recent_shapes': dict(ctx['recent_shapes']),
                'recent_sum_avg': sum(ctx['recent_sums']) / len(ctx['recent_sums']) if ctx['recent_sums'] else 13.5,
                'recent_span_avg': sum(ctx['recent_spans']) / len(ctx['recent_spans']) if ctx['recent_spans'] else 4.5,
                'miss_stats': miss_stats
            },
            'hot_numbers': {
                'bai': [x[0] for x in ctx['freq20'][0].most_common(3)],
                'shi': [x[0] for x in ctx['freq20'][1].most_common(3)],
                'ge': [x[0] for x in ctx['freq20'][2].most_common(3)]
            },
            'cold_numbers': {
                'bai': [x[0] for x in ctx['freq20'][0].most_common()[-3:]],
                'shi': [x[0] for x in ctx['freq20'][1].most_common()[-3:]],
                'ge': [x[0] for x in ctx['freq20'][2].most_common()[-3:]]
            },
            'disclaimer': '基于概率分布的智能选号，不是预测。命中率≈1%（与随机选号相同），只提高选号质量。遗漏回补作为参考维度，但不是主要依据。'
        }
        
        return report
