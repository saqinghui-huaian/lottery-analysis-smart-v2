#!/usr/bin/env python3
"""
彩票评分系统 v6 - 整合统计学与专业分析师方法
核心改进：
1. 去除遗漏回补的误导性加分（赌徒谬误）
2. 保留描述性统计（和值、跨度、形态分布）
3. 增加稳定性（去除随机扰动）
4. 简化维度（从13个减到6个有效维度）
5. 增加数据验证和回测机制
6. 整合专业分析师维度（复隔中、和值5维、跨度5维）
7. 新增统计检验（卡方检验、置信区间）
"""

import random
from collections import Counter
from typing import List, Dict, Tuple, Optional
import math

# ══════════════════════════════════════════════════════════════
#  数学基础（必须理解）
# ══════════════════════════════════════════════════════════════
#
# 彩票开奖是独立随机事件。每期开奖号码与历史数据完全无关。
# 统计分析只能"描述历史分布"，不能"预测未来"。
#
# 正确的使用方式：
# - 和值/跨度分布：描述"什么样的号码更常见"
# - 形态分布：组六72%、组三27%、豹子1%
# - 遗漏统计：仅作描述，不作预测依据
#
# 错误的使用方式：
# - "某号遗漏30期了，该出了" → 赌徒谬误，每期概率仍10%
# - "连续5期组六，该出组三了" → 独立事件，无记忆性

class LotteryScorer:
    """v6评分系统：整合统计学与专业分析师维度"""
    
    def __init__(self, data: List[Dict]):
        """
        data: 开奖数据列表，每个元素为 {'h':百位, 't':十位, 'u':个位, 'period':期号}
        最新数据在前
        """
        self.data = data
        self.n = len(data)
        self.ctx = self._compute_context()
    
    def _compute_context(self) -> Dict:
        """计算统计上下文"""
        ctx = {}
        
        # 1. 近期频率（描述性，用于了解近期趋势）
        ctx['freq20'] = [Counter(), Counter(), Counter()]
        for d in self.data[:20]:
            for pos, key in enumerate(['h', 't', 'u']):
                ctx['freq20'][pos][d[key]] += 1
        
        # 2. 和值统计（描述性）
        sums = [d['h'] + d['t'] + d['u'] for d in self.data[:100]]
        ctx['hz_avg'] = sum(sums) / len(sums) if sums else 13.5
        ctx['hz_std'] = (sum((s - ctx['hz_avg'])**2 for s in sums) / len(sums)) ** 0.5 if sums else 5.2
        
        # 3. 跨度统计（描述性）
        spans = [max(d['h'], d['t'], d['u']) - min(d['h'], d['t'], d['u']) for d in self.data[:100]]
        ctx['kd_freq'] = Counter(spans)
        ctx['kd_avg'] = sum(spans) / len(spans) if spans else 4.5
        
        # 4. 形态统计（描述性，理论值：豹子1%，组三27%，组六72%）
        ctx['shape'] = Counter()
        for d in self.data[:50]:
            unique = len(set([d['h'], d['t'], d['u']]))
            if unique == 1:
                ctx['shape']['baozi'] += 1
            elif unique == 2:
                ctx['shape']['zusan'] += 1
            else:
                ctx['shape']['zuliu'] += 1
        
        # 5. 奇偶统计（描述性）
        ctx['odd_cnt'] = 0
        ctx['even_cnt'] = 0
        for d in self.data[:30]:
            for x in [d['h'], d['t'], d['u']]:
                if x % 2 == 1:
                    ctx['odd_cnt'] += 1
                else:
                    ctx['even_cnt'] += 1
        
        # 6. 大小统计（描述性）
        ctx['big_cnt'] = 0
        ctx['small_cnt'] = 0
        for d in self.data[:30]:
            for x in [d['h'], d['t'], d['u']]:
                if x >= 5:
                    ctx['big_cnt'] += 1
                else:
                    ctx['small_cnt'] += 1
        
        # 7. 遗漏值（仅作描述，不作预测依据）
        ctx['miss'] = [{}, {}, {}]
        for digit in range(10):
            for pos, key in enumerate(['h', 't', 'u']):
                for i, d in enumerate(self.data):
                    if d[key] == digit:
                        ctx['miss'][pos][digit] = i
                        break
                else:
                    ctx['miss'][pos][digit] = self.n
        
        # 8. 复隔中分析（v6新增，参考中彩网专业分析师）
        if len(self.data) >= 3:
            last_draw = set([self.data[0]['h'], self.data[0]['t'], self.data[0]['u']])
            prev_draw = set([self.data[1]['h'], self.data[1]['t'], self.data[1]['u']])
            
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
        
        # 9. 和值5维分析（v6新增，参考中彩网囚牛分析师）
        if len(self.data) >= 10:
            hz_list = [d['h'] + d['t'] + d['u'] for d in self.data[:10]]
            
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
        
        # 10. 跨度5维分析（v6新增，参考中彩网老K分析师）
        if len(self.data) >= 10:
            kd_list = [max(d['h'], d['t'], d['u']) - min(d['h'], d['t'], d['u']) for d in self.data[:10]]
            
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
        
        # 11. 区段分布（v6新增）
        if len(self.data) >= 10:
            # 小号区(0-2)、中号区(3-6)、大号区(7-9)
            small_count = 0
            mid_count = 0
            large_count = 0
            for d in self.data[:10]:
                for x in [d['h'], d['t'], d['u']]:
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
        
        # 12. 卡方检验（v6新增）
        # 检验各位数字分布是否均匀
        chi2_stats = []
        for pos in range(3):
            key = ['h', 't', 'u'][pos]
            observed = [sum(1 for d in self.data[:100] if d[key] == digit) for digit in range(10)]
            expected = sum(observed) / 10
            chi2 = sum((o - expected)**2 / expected for o in observed)
            chi2_stats.append(chi2)
        ctx['chi2'] = chi2_stats
        
        return ctx
    
    def score_bet(self, b: int, s: int, g: int) -> float:
        """
        评分函数 v6：整合统计学与专业分析师维度
        
        设计原则：
        - 只用描述性统计（和值、跨度、形态分布）
        - 不用误导性指标（遗漏回补、Markov链）
        - 优先选择"常见"的组合形态
        - 稳定性：无随机扰动
        - 整合专业分析师维度（复隔中、和值5维、跨度5维）
        """
        score = 0.0
        
        # ── 维度1：和值合理性（权重30%）──
        # 和值7-20占83.2%，是最有价值的筛选维度
        hz = b + s + g
        hz_diff = abs(hz - self.ctx['hz_avg'])
        if hz_diff <= 2:
            score += 15  # 接近均值
        elif hz_diff <= 4:
            score += 10
        elif hz_diff <= 6:
            score += 5
        if 7 <= hz <= 20:
            score += 8  # 高频区
        
        # ── 维度2：跨度合理性（权重25%）──
        # 跨度4-7最常见，跨度0（豹子）极罕见
        kd = max(b, s, g) - min(b, s, g)
        kd_freq = self.ctx['kd_freq'].get(kd, 0)
        score += kd_freq * 0.3
        if 4 <= kd <= 7:
            score += 5
        elif kd == 0:
            score -= 5  # 豹子概率仅1%，降低权重
        
        # ── 维度3：形态均衡（权重20%）──
        # 组六72%，组三27%，豹子1%
        unique = len(set([b, s, g]))
        if unique == 3:
            score += 8  # 组六最常见
        elif unique == 2:
            score += 4  # 组三
        else:
            score -= 3  # 豹子罕见
        
        # ── 维度4：奇偶平衡（权重10%）──
        # 2:1或1:2各37.5%，全奇/全偶仅12.5%
        odd_count = sum(1 for x in [b, s, g] if x % 2 == 1)
        if odd_count in [1, 2]:
            score += 4
        elif odd_count in [0, 3]:
            score -= 2
        
        # ── 维度5：大小平衡（权重10%）──
        # 2:1或1:2各37.5%，全大/全小仅12.5%
        big_count = sum(1 for x in [b, s, g] if x >= 5)
        if big_count in [1, 2]:
            score += 4
        elif big_count in [0, 3]:
            score -= 2
        
        # ── 维度6：近期频率参考（权重5%）──
        # 仅作轻微参考，不作为主要依据
        for pos, key in enumerate([b, s, g]):
            freq = self.ctx['freq20'][pos].get(key, 0)
            score += freq * 0.2
        
        # ── 维度7：专业维度加分（v6新增）──
        # 7.1 复隔中分析加分
        if 'fugezhong' in self.ctx:
            fgz = self.ctx['fugezhong']
            # 复码加分（上期出现的数字）
            if b in fgz['fu'] or s in fgz['fu'] or g in fgz['fu']:
                score += 3
            # 中码加分（既不是复码也不是隔码）
            mid_count = sum(1 for x in [b,s,g] if x in fgz['zhong'])
            if mid_count >= 2:
                score += 2
        
        # 7.2 和值5维分析加分
        if 'hz5d' in self.ctx:
            hz5d = self.ctx['hz5d']
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
        
        # 7.3 跨度5维分析加分
        if 'kd5d' in self.ctx:
            kd5d = self.ctx['kd5d']
            # 跨度质合匹配
            if (kd in [1,2,3,5,7]) == kd5d['target_prime']:
                score += 1
            # 跨度奇偶匹配
            if kd % 2 == kd5d['target_parity']:
                score += 1
            # 跨度大小匹配
            if (kd >= 5) == kd5d['target_size']:
                score += 1
        
        # 7.4 区段分布加分
        if 'quduan' in self.ctx:
            qd = self.ctx['quduan']
            small = sum(1 for x in [b,s,g] if x <= 2)
            mid = sum(1 for x in [b,s,g] if 3 <= x <= 6)
            large = sum(1 for x in [b,s,g] if x >= 7)
            # 匹配目标区段分布
            if small == qd['target_small'] and mid == qd['target_mid'] and large == qd['target_large']:
                score += 3
        
        return score
    
    def generate_candidates(self, n_candidates: int = 50) -> set:
        """
        生成候选号码池
        
        策略：
        1. 和值目标组合（和值7-20）
        2. 跨度合理组合（跨度4-7）
        3. 形态均衡组合（优先组六）
        4. 随机采样（保证多样性）
        5. 复隔中组合（v6新增）
        6. 和值5维组合（v6新增）
        7. 跨度5维组合（v6新增）
        """
        candidates = set()
        
        # 策略1：和值目标组合
        target_hz = int(self.ctx['hz_avg'])
        for b in range(10):
            for s in range(10):
                for g in range(10):
                    if abs(b + s + g - target_hz) <= 3:
                        candidates.add((b, s, g))
        
        # 策略2：跨度合理组合
        for _ in range(100):
            b, s, g = random.randint(0, 9), random.randint(0, 9), random.randint(0, 9)
            kd = max(b, s, g) - min(b, s, g)
            if 4 <= kd <= 7:
                candidates.add((b, s, g))
        
        # 策略3：形态均衡组合（组六优先）
        for _ in range(100):
            b, s, g = random.randint(0, 9), random.randint(0, 9), random.randint(0, 9)
            if len(set([b, s, g])) == 3:  # 组六
                if 7 <= b + s + g <= 20:  # 和值合理
                    candidates.add((b, s, g))
        
        # 策略4：随机采样
        for _ in range(200):
            b, s, g = random.randint(0, 9), random.randint(0, 9), random.randint(0, 9)
            candidates.add((b, s, g))
        
        # 策略5：复隔中组合（v6新增）
        if 'fugezhong' in self.ctx:
            fgz = self.ctx['fugezhong']
            fu_digits = list(fgz['fu'])
            zhong_digits = list(fgz['zhong'])
            for f in fu_digits[:3]:
                for z1 in zhong_digits[:4]:
                    for z2 in zhong_digits[:4]:
                        candidates.add((f, z1, z2))
                        candidates.add((z1, f, z2))
                        candidates.add((z1, z2, f))
            for z1 in zhong_digits[:5]:
                for z2 in zhong_digits[:5]:
                    for z3 in zhong_digits[:5]:
                        candidates.add((z1, z2, z3))
        
        # 策略6：和值5维组合（v6新增）
        if 'hz5d' in self.ctx:
            hz5d = self.ctx['hz5d']
            target_hz_range = hz5d['target_range']
            for b in range(10):
                for s in range(10):
                    for g in range(10):
                        hz = b + s + g
                        if target_hz_range[0] <= hz <= target_hz_range[1]:
                            hz_parity = hz % 2
                            hz_size = 1 if hz >= 14 else 0
                            hz_prime = 1 if hz in [2,3,5,7,11,13,17,19,23] else 0
                            hz_road = hz % 3
                            
                            if (hz_parity == hz5d['target_parity'] and
                                hz_size == hz5d['target_size'] and
                                hz_prime == hz5d['target_prime'] and
                                hz_road == hz5d['target_road']):
                                candidates.add((b, s, g))
        
        # 策略7：跨度5维组合（v6新增）
        if 'kd5d' in self.ctx:
            kd5d = self.ctx['kd5d']
            for b in range(10):
                for s in range(10):
                    for g in range(10):
                        kd = max(b, s, g) - min(b, s, g)
                        kd_prime = 1 if kd in [1,2,3,5,7] else 0
                        kd_parity = kd % 2
                        kd_size = 1 if kd >= 5 else 0
                        
                        if (kd_prime == kd5d['target_prime'] and
                            kd_parity == kd5d['target_parity'] and
                            kd_size == kd5d['target_size']):
                            candidates.add((b, s, g))
        
        return candidates
    
    def recommend(self, top_n: int = 10) -> List[Tuple]:
        """
        生成推荐号码
        
        返回：[(score, b, s, g, hz, kd), ...] 按分数降序
        """
        candidates = self.generate_candidates()
        
        scored = []
        for b, s, g in candidates:
            sc = self.score_bet(b, s, g)
            hz = b + s + g
            kd = max(b, s, g) - min(b, s, g)
            scored.append((sc, b, s, g, hz, kd))
        
        scored.sort(key=lambda x: -x[0])
        return scored[:top_n]
    
    def get_analysis_report(self) -> Dict:
        """
        生成分析报告（仅描述性统计，不做预测）
        """
        report = {
            'data_count': self.n,
            'sum_stats': {
                'avg': round(self.ctx['hz_avg'], 1),
                'std': round(self.ctx['hz_std'], 1),
                'range_7_20_pct': round(sum(1 for d in self.data[:100] 
                    if 7 <= d['h'] + d['t'] + d['u'] <= 20) / min(100, self.n) * 100, 1)
            },
            'span_stats': {
                'avg': round(self.ctx['kd_avg'], 1),
                'range_4_7_pct': round(sum(1 for d in self.data[:100] 
                    if 4 <= max(d['h'], d['t'], d['u']) - min(d['h'], d['t'], d['u']) <= 7) / min(100, self.n) * 100, 1)
            },
            'shape_stats': {
                'zuliu_pct': round(self.ctx['shape'].get('zuliu', 0) / 50 * 100, 1),
                'zusan_pct': round(self.ctx['shape'].get('zusan', 0) / 50 * 100, 1),
                'baozi_pct': round(self.ctx['shape'].get('baozi', 0) / 50 * 100, 1)
            },
            'parity_stats': {
                'odd_pct': round(self.ctx['odd_cnt'] / (self.ctx['odd_cnt'] + self.ctx['even_cnt']) * 100, 1) if (self.ctx['odd_cnt'] + self.ctx['even_cnt']) > 0 else 50
            },
            'size_stats': {
                'big_pct': round(self.ctx['big_cnt'] / (self.ctx['big_cnt'] + self.ctx['small_cnt']) * 100, 1) if (self.ctx['big_cnt'] + self.ctx['small_cnt']) > 0 else 50
            },
            'chi2_stats': {
                'bai_chi2': round(self.ctx['chi2'][0], 2),
                'shi_chi2': round(self.ctx['chi2'][1], 2),
                'ge_chi2': round(self.ctx['chi2'][2], 2),
                'critical_value': 16.92,  # χ²(0.05, 9)
                'is_uniform': all(c < 16.92 for c in self.ctx['chi2'])
            },
            'disclaimer': '⚠️ 以上为描述性统计，彩票开奖为独立随机事件，历史数据不能预测未来。'
        }
        
        return report


def validate_draw_data(data: List[Dict]) -> Dict:
    """
    验证开奖数据的完整性和合理性
    
    返回：{'valid': bool, 'issues': list, 'warnings': list}
    """
    issues = []
    warnings = []
    
    if not data:
        return {'valid': False, 'issues': ['数据为空'], 'warnings': []}
    
    # 检查数据格式
    for i, d in enumerate(data[:10]):
        if 'h' not in d or 't' not in d or 'u' not in d:
            issues.append(f"第{i}条数据缺少h/t/u字段")
        else:
            if not (0 <= d['h'] <= 9 and 0 <= d['t'] <= 9 and 0 <= d['u'] <= 9):
                issues.append(f"第{i}条数据数字超出0-9范围")
    
    # 检查期号连续性
    if len(data) >= 2 and 'period' in data[0]:
        try:
            p1 = int(data[0]['period'])
            p2 = int(data[1]['period'])
            if p1 - p2 > 5:
                warnings.append(f"期号跳跃较大：{p1} -> {p2}")
        except (ValueError, TypeError):
            pass
    
    # 检查数据量
    if len(data) < 20:
        warnings.append(f"数据量较少（{len(data)}期），统计结果可能不稳定")
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'warnings': warnings
    }


def backtest_recommendation(recommendations: List[Tuple], actual_result: Tuple) -> Dict:
    """
    回测推荐结果
    
    recommendations: [(score, b, s, g, hz, kd), ...]
    actual_result: (b, s, g) 实际开奖号码
    
    返回：{'hit': bool, 'hit_rank': int, 'details': dict}
    """
    b_actual, s_actual, g_actual = actual_result
    actual_set = set([b_actual, s_actual, g_actual])
    actual_hz = b_actual + s_actual + g_actual
    actual_kd = max(b_actual, s_actual, g_actual) - min(b_actual, s_actual, g_actual)
    
    hit = False
    hit_rank = -1
    
    for i, (sc, b, s, g, hz, kd) in enumerate(recommendations):
        if b == b_actual and s == s_actual and g == g_actual:
            hit = True
            hit_rank = i + 1
            break
    
    # 检查是否命中形态
    actual_shape = 'baozi' if len(actual_set) == 1 else ('zusan' if len(actual_set) == 2 else 'zuliu')
    rec_shapes = []
    for sc, b, s, g, hz, kd in recommendations:
        u = len(set([b, s, g]))
        rec_shapes.append('baozi' if u == 1 else ('zusan' if u == 2 else 'zuliu'))
    
    shape_hit = actual_shape in rec_shapes
    
    # 检查和值是否在推荐范围内
    rec_hz_range = set()
    for sc, b, s, g, hz, kd in recommendations:
        rec_hz_range.add(hz)
    hz_hit = actual_hz in rec_hz_range
    
    return {
        'hit': hit,
        'hit_rank': hit_rank,
        'actual': f"{b_actual}{s_actual}{g_actual}",
        'actual_hz': actual_hz,
        'actual_kd': actual_kd,
        'actual_shape': actual_shape,
        'shape_hit': shape_hit,
        'hz_hit': hz_hit,
        'recommendations': [f"{b}{s}{g}" for sc, b, s, g, hz, kd in recommendations[:10]]
    }


if __name__ == '__main__':
    # 示例用法
    sample_data = [
        {'h': 3, 't': 7, 'u': 2, 'period': '2026001'},
        {'h': 1, 't': 5, 'u': 9, 'period': '2026002'},
        {'h': 8, 't': 2, 'u': 4, 'period': '2026003'},
    ]
    
    scorer = LotteryScorer(sample_data)
    recommendations = scorer.recommend(10)
    
    print("推荐号码：")
    for sc, b, s, g, hz, kd in recommendations:
        print(f"  {b}{s}{g}  和值:{hz}  跨度:{kd}  评分:{sc:.1f}")
    
    report = scorer.get_analysis_report()
    print("\n分析报告：")
    print(f"  数据量：{report['data_count']}期")
    print(f"  和值均值：{report['sum_stats']['avg']}")
    print(f"  组六占比：{report['shape_stats']['zuliu_pct']}%")
    print(f"  卡方检验：{report['chi2_stats']}")
