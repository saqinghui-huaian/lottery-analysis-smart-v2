#!/usr/bin/env python3
"""
彩票推荐脚本 v3 - 基于多策略加权评分生成参考号码

与 lottery_analysis.py 的 recommend() 函数使用相同的评分逻辑。
可独立运行，也可作为模块导入。

Usage:
    python3 recommend.py <数据文件.json> [top_n]

输入: lottery_analysis.py 输出的JSON文件
输出: 推荐号码列表（JSON格式）

数学基础:
- 组六72%, 组三27%, 豹子1%
- 遗漏≥15期(P=20.6%)值得关注
- 重号27.1%, 连号43.8%
- 和值均值13.5, 高频区7-20(83.2%)
"""

import json
import sys
import random
from collections import Counter
from itertools import product


def load_analysis(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_context_from_digits(digits_list):
    """从数字列表计算统计上下文。
    digits_list: [[b,s,g], [b,s,g], ...] 最新在前
    """
    ctx = {}
    n = len(digits_list)

    # 各位频率
    ctx['freq20'] = [Counter(), Counter(), Counter()]
    for d in digits_list[:20]:
        for pos in range(3):
            ctx['freq20'][pos][d[pos]] += 1

    # 加权热度
    ctx['weighted'] = Counter()
    for d in digits_list[:20]:
        for x in d: ctx['weighted'][x] += 5
    for d in digits_list[20:50]:
        for x in d: ctx['weighted'][x] += 3
    for d in digits_list[50:]:
        for x in d: ctx['weighted'][x] += 1

    # 遗漏值
    ctx['miss'] = [{}, {}, {}]
    for digit in range(10):
        for pos in range(3):
            for i, d in enumerate(digits_list):
                if d[pos] == digit:
                    ctx['miss'][pos][digit] = i
                    break
            else:
                ctx['miss'][pos][digit] = n

    # 和值统计
    sums = [sum(d) for d in digits_list[:50]]
    ctx['hz_avg'] = sum(sums) / max(len(sums), 1)

    # 跨度统计
    spans = [max(d) - min(d) for d in digits_list[:50]]
    ctx['kd_freq'] = Counter(spans)

    # 012路
    def road(x): return x % 3
    ctx['road20'] = [Counter(), Counter(), Counter()]
    for d in digits_list[:20]:
        for pos in range(3):
            ctx['road20'][pos][road(d[pos])] += 1

    return ctx


def score_bet(b, s, g, ctx):
    """v3评分: 13个维度"""
    score = 0.0

    # 1. 加权热度
    heat = ctx['weighted'].get(b, 0) + ctx['weighted'].get(s, 0) + ctx['weighted'].get(g, 0)
    score += heat * 0.10

    # 2. 位置频率
    score += ctx['freq20'][0].get(b, 0) * 2.0
    score += ctx['freq20'][1].get(s, 0) * 2.0
    score += ctx['freq20'][2].get(g, 0) * 2.0

    # 3. 遗漏回补 (≥15期)
    for pos, digit in enumerate([b, s, g]):
        m = ctx['miss'][pos].get(digit, 0)
        if m >= 15:
            score += min(m, 30) * 0.3
        if m >= 20:
            score += 4
        if m >= 30:
            score += 3

    # 4. 012路
    def road(x): return x % 3
    for pos, digit in enumerate([b, s, g]):
        score += ctx['road20'][pos].get(road(digit), 0) * 0.8

    # 5. 和值
    hz = b + s + g
    hz_diff = abs(hz - ctx['hz_avg'])
    if hz_diff <= 2: score += 8
    elif hz_diff <= 4: score += 5
    elif hz_diff <= 6: score += 2
    if 7 <= hz <= 20: score += 3

    # 6. 跨度
    kd = max(b, s, g) - min(b, s, g)
    score += ctx['kd_freq'].get(kd, 0) * 0.6
    if 4 <= kd <= 7: score += 2

    # 7. 形态 (组六72%, 组三27%)
    unique = len(set([b, s, g]))
    if unique == 3: score += 4
    elif unique == 2: score += 2

    # 8. 奇偶 (2:1/1:2各37.5%)
    odd_count = sum(1 for x in [b, s, g] if x % 2 == 1)
    if odd_count in [1, 2]: score += 2

    # 9. 大小
    big_count = sum(1 for x in [b, s, g] if x >= 5)
    if big_count in [1, 2]: score += 2

    # 10. 连号 (43.8%)
    digits = sorted([b, s, g])
    for i in range(2):
        if digits[i + 1] - digits[i] == 1:
            score += 2
            break

    # 11. 冷号回补
    total_miss = sum(ctx['miss'][pos].get(d, 0) for pos, d in enumerate([b, s, g]))
    if total_miss >= 45: score += 5
    if total_miss >= 60: score += 3

    return score


def generate_recommendations(digits_list, top_n=10):
    """生成推荐号码 (v3多策略评分)"""
    ctx = compute_context_from_digits(digits_list)

    # 8种候选策略
    candidates = set()

    # 策略1: 位置热号
    top_bai = [x[0] for x in ctx['freq20'][0].most_common(6)]
    top_shi = [x[0] for x in ctx['freq20'][1].most_common(6)]
    top_ge = [x[0] for x in ctx['freq20'][2].most_common(6)]
    for b in top_bai:
        for s in top_shi:
            for g in top_ge:
                candidates.add((b, s, g))

    # 策略2: 加权热度
    top7 = [x[0] for x in ctx['weighted'].most_common(7)]
    for b in top7:
        for s in top7:
            for g in top7:
                candidates.add((b, s, g))

    # 策略3: 遗漏回补 (≥15期)
    for pos in range(3):
        high_miss = sorted(ctx['miss'][pos].items(), key=lambda x: -x[1])
        high_miss = [(d, m) for d, m in high_miss if m >= 15][:4]
        for d, _ in high_miss:
            for h in top7:
                for h2 in top7:
                    combo = [h, h2, h2]
                    combo[pos] = d
                    candidates.add(tuple(combo))

    # 策略4: 和值目标
    target_hz = int(ctx['hz_avg'])
    for b in range(10):
        for s in range(10):
            for g in range(10):
                if abs(b + s + g - target_hz) <= 3:
                    candidates.add((b, s, g))

    # 策略5: 012路
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

    # 策略6: 冷号回补
    cold_digits = [[], [], []]
    for pos in range(3):
        avg_miss = sum(ctx['miss'][pos].values()) / 10
        for d in range(10):
            if ctx['miss'][pos].get(d, 0) > avg_miss * 2:
                cold_digits[pos].append(d)
    for b in cold_digits[0][:3]:
        for s in cold_digits[1][:3]:
            for g in cold_digits[2][:3]:
                candidates.add((b, s, g))

    # 策略7: 组三候选
    zusan_recent = sum(1 for d in digits_list[:5] if len(set(d)) == 2)
    if zusan_recent == 0:
        for d1 in top7[:5]:
            for d2 in top7[:5]:
                if d1 != d2:
                    candidates.add((d1, d1, d2))
                    candidates.add((d1, d2, d1))
                    candidates.add((d2, d1, d1))

    # 评分
    scored = []
    for b, s, g in candidates:
        sc = score_bet(b, s, g, ctx)
        hz = b + s + g
        kd = max(b, s, g) - min(b, s, g)
        scored.append({
            "number": f"{b}{s}{g}",
            "sum": hz,
            "span": kd,
            "score": round(sc, 1),
        })

    scored.sort(key=lambda x: -x["score"])
    return scored[:top_n]


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 recommend.py <数据文件.json> [top_n]")
        print("输入文件: lottery_analysis.py --recommend 的输出")
        sys.exit(1)

    filepath = sys.argv[1]
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    analysis = load_analysis(filepath)

    # 尝试从分析结果中提取数字列表
    if 'recent' in analysis:
        digits_list = analysis['recent']
    elif 'recommendations' in analysis:
        # 已有推荐，直接展示
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
        return
    else:
        print("Error: 无法从输入文件中提取数字数据")
        sys.exit(1)

    results = generate_recommendations(digits_list, top_n)

    output = {
        "recommendations": results,
        "method": "v3多策略加权评分(13维)",
        "disclaimer": "⚠️ 基于历史统计，非预测。彩票独立随机，请理性投注。",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
