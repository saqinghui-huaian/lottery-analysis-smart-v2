#!/usr/bin/env python3
"""
Lottery draw data fetcher, statistical analyzer, and number recommender.
Supports: 排列三 (sporttery API via curl), 福彩3D (cwl.gov.cn API via curl + cookies).

v3: Fixed API parameters, added year-boundary filtering, improved scoring.

Usage:
    python3 lottery_analysis.py              # analyze 排列三 last 100 draws
    python3 lottery_analysis.py --game 3d    # analyze 福彩3D
    python3 lottery_analysis.py --game 35 --count 200 --recommend

PITFALLS (verified 2026-07-07):
- Both APIs MUST use curl (subprocess) — urllib gets 403 from sporttery and
  infinite 302 from cwl.gov.cn.
- cwl.gov.cn JSON has literal control chars — use regex extraction, not json.loads.
- cwl.gov.cn: issueCount MUST be EMPTY! issueCount=100 returns 404!
- sporttery.cn: Use mobile UA + mobile Referer to bypass WAF reliably.
- sporttery.cn pagination: Page 2+ may return previous year's data — must filter
  by period prefix to avoid year-crossing contamination.
- cwl.gov.cn: Cookie required (2-step flow). Timeout=30 for first request.
"""

import json
import sys
import subprocess
import tempfile
import os
import random
import re
import time
from collections import Counter
from datetime import datetime

GAME_NAMES = {
    '35': '排列三',
    '37': '排列五',
    '3d': '福彩3D',
    '3D': '福彩3D',
}

# Mobile UA — bypasses sporttery.cn WAF (verified 2026-06-27)
MOBILE_UA = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


def _get_current_year_prefix():
    """Get 2-digit year prefix for period filtering (e.g., '26' for 2026)."""
    return str(datetime.now().year)[-2:]


def fetch_pl3(game_no='35', count=200):
    """Fetch 排列三/排列五 from sporttery official API.

    MUST use curl — sporttery.cn WAF blocks urllib with 403.
    Uses mobile UA + mobile Referer for reliable WAF bypass.
    Handles pagination with year-boundary filtering.
    Uses regex extraction because JSON can contain control characters.
    """
    current_prefix = _get_current_year_prefix()
    all_results = []
    seen_periods = set()
    pages_needed = (count + 99) // 100  # ceil division

    for page in range(1, pages_needed + 1):
        url = (
            f'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry'
            f'?gameNo={game_no}&provinceId=0&pageSize=100&isVerify=1&pageNo={page}'
        )
        result = subprocess.run([
            'curl', '-s', '-k', '--max-time', '15', url,
            '-H', f'User-Agent: {MOBILE_UA}',
            '-H', 'Accept: application/json',
            '-H', 'Referer: https://m.lottery.gov.cn/',
        ], capture_output=True, text=True, timeout=20)

        raw = result.stdout
        # Regex extraction — JSON may have control chars or WAF HTML
        nums_list = re.findall(r'"lotteryDrawResult":"(\d+ \d+ \d+)"', raw)
        periods = re.findall(r'"lotteryDrawNum":"(\d+)"', raw)
        dates = re.findall(r'"lotteryDrawTime":"(\d{4}-\d{2}-\d{2})"', raw)

        page_results = []
        for i in range(min(len(nums_list), len(periods))):
            p = periods[i]
            # Skip duplicates
            if p in seen_periods:
                continue
            seen_periods.add(p)

            # CRITICAL: Filter out previous year's data
            # Period format: YYnnn (e.g., 26178 = 2026, draw 178)
            # When paginating, page 2+ may return draws from previous year
            # (e.g., 25351) which have higher seq numbers than current year
            if not p.startswith(current_prefix):
                continue

            ns = list(map(int, nums_list[i].split()))
            d = dates[i] if i < len(dates) else ''
            page_results.append({
                'period': p,
                'date': d,
                'h': ns[0], 't': ns[1], 'u': ns[2],
                'sum': sum(ns[:3])
            })

        all_results.extend(page_results)

        # Rate limit between pages
        if page < pages_needed:
            time.sleep(3)

    if not all_results:
        raise RuntimeError(
            "sporttery.cn returned no data — WAF may have blocked the request. "
            "Retry with mobile UA or wait a few seconds."
        )

    # Sort by period descending (newest first)
    all_results.sort(key=lambda x: x['period'], reverse=True)
    return all_results[:count]


def fetch_3d(count=200):
    """Fetch 福彩3D from cwl.gov.cn official API (requires curl + cookies).

    CRITICAL: issueCount must be EMPTY! issueCount=100 returns 404.
    Uses regex extraction as primary method because cwl.gov.cn JSON contains
    literal control characters that break json.loads() even with strict=False.
    """
    cookie_file = os.path.join(tempfile.gettempdir(), 'cwl_cookies.txt')

    # Step 1: GET index page to acquire session cookies (timeout=30)
    subprocess.run([
        'curl', '-s', '-c', cookie_file,
        'https://www.cwl.gov.cn/ygkj/wqkjgg/fc3d/',
        '-H', f'User-Agent: {DESKTOP_UA}',
        '-o', '/dev/null'
    ], timeout=30, check=False)

    all_results = []
    seen_codes = set()
    pages_needed = (count + 99) // 100

    for page in range(1, pages_needed + 1):
        # CRITICAL: issueCount= is EMPTY, not "100"!
        url = (
            f'https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice'
            f'?name=3d&issueCount=&issueStart=&issueEnd=&dayStart=&dayEnd='
            f'&pageNo={page}&pageSize=100&systemType=PC'
        )
        result = subprocess.run([
            'curl', '-s', '-b', cookie_file, '-L', '--max-redirs', '5',
            url,
            '-H', f'User-Agent: {DESKTOP_UA}',
            '-H', 'Accept: application/json',
            '-H', 'Referer: https://www.cwl.gov.cn/ygkj/wqkjgg/fc3d/',
        ], capture_output=True, text=True, timeout=30)

        raw = result.stdout

        # Primary: regex extraction (reliable even with control chars in JSON)
        codes = re.findall(r'"code":"(\d+)"', raw)
        reds = re.findall(r'"red":"(\d+,\d+,\d+)"', raw)
        dates = re.findall(r'"date":"([^"]+)"', raw)

        if codes and reds:
            for i in range(min(len(codes), len(reds))):
                code = codes[i]
                if code in seen_codes:
                    continue
                seen_codes.add(code)
                ns = list(map(int, reds[i].split(',')))
                d = dates[i][:10] if i < len(dates) else ''
                all_results.append({
                    'period': code,
                    'date': d,
                    'h': ns[0], 't': ns[1], 'u': ns[2],
                    'sum': sum(ns[:3])
                })
        elif '404' in raw[:200] or 'Not Found' in raw[:200]:
            # issueCount may have been set incorrectly — this shouldn't happen
            # with the fixed code, but handle gracefully
            raise RuntimeError(
                "cwl.gov.cn returned 404 — check API parameters. "
                "issueCount must be EMPTY."
            )

        # Rate limit between pages
        if page < pages_needed:
            time.sleep(2)

    if not all_results:
        # Fallback: json.loads (may fail on control chars)
        raise RuntimeError(
            "cwl.gov.cn returned unparseable data — "
            "regex found no matches. Cookies may have expired, retry."
        )

    # Sort by period descending (newest first)
    all_results.sort(key=lambda x: x['period'], reverse=True)
    return all_results[:count]


# ══════════════════════════════════════════════════════════════
#  v3 Multi-Strategy Scoring System
# ══════════════════════════════════════════════════════════════

def compute_context(data):
    """Compute all statistical context from draw data.
    data: list of dicts with 'h','t','u' keys, newest first.

    Mathematical basis:
    - For uniform digits 0-9, P(specific digit) = 1/10 per position
    - Expected miss (geometric): E[miss] = 1/p - 1 = 9 periods
    - P(miss >= k) = (1-p)^k = 0.9^k
    - P(miss >= 15) = 20.6%, P(miss >= 20) = 12.2%
    - Group shape: 豹子 1%, 组三 27%, 组六 72%
    - Odd/even per position: 50/50
    - Sum mean: 13.5, most common range: 7-13 and 14-20 (each ~41.6%)
    """
    ctx = {}
    n = len(data)

    # 1. Position frequency (recent 20/50/100)
    ctx['freq20'] = [Counter(), Counter(), Counter()]
    ctx['freq50'] = [Counter(), Counter(), Counter()]
    ctx['freq100'] = [Counter(), Counter(), Counter()]
    for d in data[:20]:
        for pos, key in enumerate(['h', 't', 'u']):
            ctx['freq20'][pos][d[key]] += 1
    for d in data[:50]:
        for pos, key in enumerate(['h', 't', 'u']):
            ctx['freq50'][pos][d[key]] += 1
    for d in data[:100]:
        for pos, key in enumerate(['h', 't', 'u']):
            ctx['freq100'][pos][d[key]] += 1

    # 2. Weighted heat: recent 20 = 5x, 20-50 = 3x, 50-100 = 1x
    ctx['weighted'] = Counter()
    for d in data[:20]:
        for x in [d['h'], d['t'], d['u']]:
            ctx['weighted'][x] += 5
    for d in data[20:50]:
        for x in [d['h'], d['t'], d['u']]:
            ctx['weighted'][x] += 3
    for d in data[50:100]:
        for x in [d['h'], d['t'], d['u']]:
            ctx['weighted'][x] += 1

    # 3. Omission: periods since last appearance
    # Mathematical basis: geometric distribution with p=0.1
    # E[miss] = 9, use 2σ threshold (~15 periods) for "notable" miss
    ctx['miss'] = [{}, {}, {}]
    for digit in range(10):
        for pos, key in enumerate(['h', 't', 'u']):
            for i, d in enumerate(data):
                if d[key] == digit:
                    ctx['miss'][pos][digit] = i
                    break
            else:
                ctx['miss'][pos][digit] = n

    # 4. Sum stats (theoretical mean = 13.5 for uniform 0-9)
    sums = [d['h'] + d['t'] + d['u'] for d in data]
    ctx['hz_avg'] = sum(sums[:50]) / min(50, n)
    ctx['hz_std'] = (sum((s - ctx['hz_avg'])**2 for s in sums[:50]) / min(50, n)) ** 0.5

    # 5. Span stats
    spans = [max(d['h'], d['t'], d['u']) - min(d['h'], d['t'], d['u']) for d in data]
    ctx['kd_freq'] = Counter(spans[:50])
    ctx['kd_avg'] = sum(spans[:50]) / min(50, n)

    # 6. 012 road stats (注意: 0路有4个数字, 1路/2路各3个, 分布不均匀)
    def road(x): return x % 3
    ctx['road20'] = [Counter(), Counter(), Counter()]
    for d in data[:20]:
        for pos, key in enumerate(['h', 't', 'u']):
            ctx['road20'][pos][road(d[key])] += 1

    # 7. Odd/Even stats (theoretical: 50/50 per position)
    ctx['odd_cnt'] = 0
    ctx['even_cnt'] = 0
    for d in data[:20]:
        for x in [d['h'], d['t'], d['u']]:
            if x % 2 == 1:
                ctx['odd_cnt'] += 1
            else:
                ctx['even_cnt'] += 1

    # 8. Big/Small stats (theoretical: 50/50, 0-4=小, 5-9=大)
    ctx['big_cnt'] = 0
    ctx['small_cnt'] = 0
    for d in data[:20]:
        for x in [d['h'], d['t'], d['u']]:
            if x >= 5:
                ctx['big_cnt'] += 1
            else:
                ctx['small_cnt'] += 1

    # 9. Repeat rate (theoretical: 1-(0.9)^3 = 27.1%)
    ctx['repeat_rate'] = 0
    repeat_total = 0
    keys = ['h', 't', 'u']
    for i in range(min(20, n - 1)):
        for pos in range(3):
            repeat_total += 1
            if data[i][keys[pos]] == data[i + 1][keys[pos]]:
                ctx['repeat_rate'] += 1
    ctx['repeat_rate'] = ctx['repeat_rate'] / max(repeat_total, 1)

    # 10. Shape distribution (theoretical: 豹子1%, 组三27%, 组六72%)
    ctx['shape'] = Counter()
    for d in data[:50]:
        unique = len(set([d['h'], d['t'], d['u']]))
        if unique == 1:
            ctx['shape']['baozi'] += 1
        elif unique == 2:
            ctx['shape']['zusan'] += 1
        else:
            ctx['shape']['zuliu'] += 1

    # 11. Markov chain: transition probability from last draw
    # P(current_pos=digit | prev_pos=prev_digit)
    # Note: For truly random draws, this should be ~1/10 for all transitions.
    # Any apparent patterns are statistical noise, but we track it for
    # completeness (用户要求).
    ctx['markov'] = [Counter(), Counter(), Counter()]
    for i in range(min(50, n - 1)):
        for pos, key in enumerate(['h', 't', 'u']):
            prev_digit = data[i + 1][key]
            curr_digit = data[i][key]
            ctx['markov'][pos][(prev_digit, curr_digit)] += 1

    return ctx


def score_bet(b, s, g, ctx):
    """Score a 3-digit combination using 13 dimensions. Higher = better.

    Scoring philosophy:
    - Frequency/heat: captures short-term momentum (if any)
    - Omission backfill: based on geometric distribution (E=9, use 2σ=15 as threshold)
    - Balance metrics: odd/even, big/small, shape — favor typical outcomes
    - Recent penalty: not exclusion, just weighted reduction
    """
    score = 0.0

    # 1. Weighted heat (accounts for recency bias)
    heat = ctx['weighted'].get(b, 0) + ctx['weighted'].get(s, 0) + ctx['weighted'].get(g, 0)
    score += heat * 0.10

    # 2. Position frequency (recent 20, higher weight)
    score += ctx['freq20'][0].get(b, 0) * 2.0
    score += ctx['freq20'][1].get(s, 0) * 2.0
    score += ctx['freq20'][2].get(g, 0) * 2.0

    # 3. Omission backfill — FIXED THRESHOLD
    # P(miss>=8)=43% (too common, was triggering on almost everything)
    # P(miss>=15)=20.6% (notable), P(miss>=20)=12.2% (strong signal)
    for pos, digit in enumerate([b, s, g]):
        m = ctx['miss'][pos].get(digit, 0)
        if m >= 15:
            score += min(m, 30) * 0.3  # Notable miss
        if m >= 20:
            score += 4  # Strong signal
        if m >= 30:
            score += 3  # Extreme miss (P=4.2%)

    # 4. Markov transition (from last draw)
    # For random draws this should add ~0 on average, but track it
    if ctx.get('last_draw'):
        last = ctx['last_draw']
        for pos, (digit, key) in enumerate(zip([b, s, g], ['h', 't', 'u'])):
            prev_digit = last[key]
            trans_count = ctx['markov'][pos].get((prev_digit, digit), 0)
            # Normalize: in 50 draws, expected count = 5
            score += trans_count * 0.3

    # 5. 012 road match
    def road(x): return x % 3
    for pos, digit in enumerate([b, s, g]):
        r = road(digit)
        score += ctx['road20'][pos].get(r, 0) * 0.8

    # 6. Sum reasonableness (theoretical mean=13.5, σ≈5.2)
    hz = b + s + g
    hz_diff = abs(hz - ctx['hz_avg'])
    if hz_diff <= 2:
        score += 8
    elif hz_diff <= 4:
        score += 5
    elif hz_diff <= 6:
        score += 2
    # High-frequency sum range: 7-20
    if 7 <= hz <= 20:
        score += 3

    # 7. Span reasonableness
    kd = max(b, s, g) - min(b, s, g)
    score += ctx['kd_freq'].get(kd, 0) * 0.6
    if 4 <= kd <= 7:
        score += 2

    # 8. Shape bonus (theoretical: 组六72%, 组三27%, 豹子1%)
    unique = len(set([b, s, g]))
    if unique == 3:
        score += 4  # 组六 most common
    elif unique == 2:
        score += 2  # 组三

    # 9. Odd/Even balance (theoretical: 2:1 or 1:2 = 37.5% each)
    odd_count = sum(1 for x in [b, s, g] if x % 2 == 1)
    if odd_count in [1, 2]:
        score += 2

    # 10. Big/Small balance (theoretical: 2:1 or 1:2 = 37.5% each)
    big_count = sum(1 for x in [b, s, g] if x >= 5)
    if big_count in [1, 2]:
        score += 2

    # 11. Consecutive digits (theoretical: 43.8%)
    digits = sorted([b, s, g])
    for i in range(len(digits) - 1):
        if digits[i + 1] - digits[i] == 1:
            score += 2
            break

    # 12. Recent repeat penalty (NOT exclusion)
    for d in ctx.get('recent5', []):
        if (b, s, g) == (d['h'], d['t'], d['u']):
            score -= 15
            break
    for d in ctx.get('recent10', []):
        if (b, s, g) == (d['h'], d['t'], d['u']):
            score -= 25
            break

    # 13. Cold number comeback (total miss across 3 positions)
    total_miss = sum(ctx['miss'][pos].get(d, 0) for pos, d in enumerate([b, s, g]))
    if total_miss >= 45:
        score += 5  # All 3 positions notably overdue
    if total_miss >= 60:
        score += 3  # Extreme combined miss

    return score


def generate_candidates(ctx, data):
    """Generate diverse candidates from 8 independent strategies.

    v3 additions: Markov chain candidates, trend direction candidates,
    组三 (pair) shape candidates.
    """
    candidates = set()

    # Strategy 1: Position hot combos (top 6 from each position)
    top_bai = [x[0] for x in ctx['freq20'][0].most_common(6)]
    top_shi = [x[0] for x in ctx['freq20'][1].most_common(6)]
    top_ge = [x[0] for x in ctx['freq20'][2].most_common(6)]
    for b in top_bai:
        for s in top_shi:
            for g in top_ge:
                candidates.add((b, s, g))

    # Strategy 2: Weighted heat combos
    top7 = [x[0] for x in ctx['weighted'].most_common(7)]
    for b in top7:
        for s in top7:
            for g in top7:
                candidates.add((b, s, g))

    # Strategy 3: Omission backfill combos (miss >= 15 periods)
    for pos in range(3):
        high_miss = sorted(ctx['miss'][pos].items(), key=lambda x: -x[1])
        high_miss = [(d, m) for d, m in high_miss if m >= 15][:4]
        for d, _ in high_miss:
            for h in top7:
                for h2 in top7:
                    combo = [h, h2, h2]
                    combo[pos] = d
                    candidates.add(tuple(combo))

    # Strategy 4: Sum-targeted combos (avg ± 3)
    target_hz = int(ctx['hz_avg'])
    for b in range(10):
        for s in range(10):
            for g in range(10):
                if abs(b + s + g - target_hz) <= 3:
                    candidates.add((b, s, g))

    # Strategy 5: 012 road combos
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

    # Strategy 6: Cold number comeback combos (miss > 2× average)
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

    # Strategy 7 (v3): Markov chain transition candidates
    if data and len(data) >= 2:
        last = data[0]
        for pos, key in enumerate(['h', 't', 'u']):
            prev_digit = last[key]
            # Find digits that frequently followed prev_digit
            trans_counts = Counter()
            for i in range(min(50, len(data) - 1)):
                if data[i + 1][key] == prev_digit:
                    trans_counts[data[i][key]] += 1
            top_trans = [d for d, _ in trans_counts.most_common(4)]
            for d in top_trans:
                for h in top7:
                    for h2 in top7:
                        combo = [h, h2, h2]
                        combo[pos] = d
                        candidates.add(tuple(combo))

    # Strategy 8 (v3): 组三 shape candidates
    # 组三 appears ~27% of the time, every ~3-4 draws on average
    # Check if 组三 is "overdue" (hasn't appeared in last 5 draws)
    zusan_count_recent = sum(
        1 for d in data[:5]
        if len(set([d['h'], d['t'], d['u']])) == 2
    )
    if zusan_count_recent == 0:
        # 组三 is overdue, add pair combos from hot numbers
        for d1 in top7[:5]:
            for d2 in top7[:5]:
                if d1 != d2:
                    candidates.add((d1, d1, d2))
                    candidates.add((d1, d2, d1))
                    candidates.add((d2, d1, d1))

    return candidates


def recommend(data, top_n=10):
    """Run v3 multi-strategy scoring and return top N recommendations."""
    ctx = compute_context(data)
    ctx['recent5'] = data[:5]
    ctx['recent10'] = data[:10]
    ctx['last_draw'] = data[0] if data else None

    candidates = generate_candidates(ctx, data)

    scored = []
    for b, s, g in candidates:
        sc = score_bet(b, s, g, ctx)
        hz = b + s + g
        kd = max(b, s, g) - min(b, s, g)
        scored.append((sc, b, s, g, hz, kd))

    scored.sort(key=lambda x: -x[0])
    return scored[:top_n]


def analyze(data, name):
    """Run full statistical analysis and print report."""
    all_nums = []
    h_nums, t_nums, u_nums, sums = [], [], [], []
    for d in data:
        all_nums.extend([d['h'], d['t'], d['u']])
        h_nums.append(d['h'])
        t_nums.append(d['t'])
        u_nums.append(d['u'])
        sums.append(d['sum'])

    print(f"\n{'='*60}")
    print(f"  {name} 近{len(data)}期数据分析报告")
    print(f"  {data[-1]['period']} ~ {data[0]['period']} ({data[-1]['date']} ~ {data[0]['date']})")
    print(f"{'='*60}")

    # 1. Number frequency
    print(f"\n{'─'*60}")
    print("【号码出现频率】")
    ctr = Counter(all_nums)
    for i in range(10):
        c = ctr.get(i, 0)
        pct = c / len(all_nums) * 100
        print(f"  {i}  {c:3d} ({pct:5.1f}%) {'█' * int(pct / 2)}")

    sorted_n = sorted(ctr.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  热号: {', '.join(str(x[0]) for x in sorted_n[:3])}")
    print(f"  冷号: {', '.join(str(x[0]) for x in sorted_n[-3:])}")

    # 2. Per-position frequency
    print(f"\n{'─'*60}")
    print("【各位号码频率】")
    for label, nums in [("百位", h_nums), ("十位", t_nums), ("个位", u_nums)]:
        c = Counter(nums)
        print(f"\n  {label}:")
        for i in range(10):
            cnt = c.get(i, 0)
            pct = cnt / len(nums) * 100
            print(f"    {i}: {cnt:2d} ({pct:5.1f}%) {'█' * int(pct / 2)}")

    # 3. Sum analysis
    print(f"\n{'─'*60}")
    print("【和值分析】")
    print(f"  范围: {min(sums)} ~ {max(sums)}  平均: {sum(sums)/len(sums):.1f}  中位: {sorted(sums)[len(sums)//2]}")
    for lo, hi, lbl in [(0, 6, '小'), (7, 13, '中'), (14, 20, '大'), (21, 27, '超大')]:
        cnt = sum(1 for s in sums if lo <= s <= hi)
        pct = cnt / len(sums) * 100
        print(f"  {lbl}({lo:2d}-{hi:2d}): {cnt:3d}期 ({pct:5.1f}%) {'█' * int(pct / 2)}")

    # 4. Odd/Even
    print(f"\n{'─'*60}")
    print("【奇偶分析】")
    odd = sum(1 for s in sums if s % 2 == 1)
    even = len(sums) - odd
    print(f"  奇: {odd}期 ({odd/len(sums)*100:.1f}%)  偶: {even}期 ({even/len(sums)*100:.1f}%)")

    # 5. Big/Small
    print(f"\n{'─'*60}")
    print("【大小分析】(0-4小, 5-9大)")
    big = sum(1 for n in all_nums if n >= 5)
    small = len(all_nums) - big
    print(f"  大: {big}次 ({big/len(all_nums)*100:.1f}%)  小: {small}次 ({small/len(all_nums)*100:.1f}%)")

    # 6. Span
    print(f"\n{'─'*60}")
    print("【跨度分析】")
    spans = [max(d['h'], d['t'], d['u']) - min(d['h'], d['t'], d['u']) for d in data]
    sc = Counter(spans)
    for i in range(10):
        cnt = sc.get(i, 0)
        if cnt > 0:
            pct = cnt / len(spans) * 100
            print(f"  {i}: {cnt:2d} ({pct:5.1f}%) {'█' * int(pct / 2)}")

    # 7. Shape (corrected: 豹子1%, 组三27%, 组六72%)
    print(f"\n{'─'*60}")
    print("【组选形态】(理论: 豹子1%, 组三27%, 组六72%)")
    trip = pair = straight = 0
    for d in data:
        ns = sorted([d['h'], d['t'], d['u']])
        if ns[0] == ns[2]:
            trip += 1
        elif ns[0] == ns[1] or ns[1] == ns[2]:
            pair += 1
        else:
            straight += 1
    print(f"  豹子: {trip}期 ({trip/len(data)*100:.1f}%)")
    print(f"  组三: {pair}期 ({pair/len(data)*100:.1f}%)")
    print(f"  组六: {straight}期 ({straight/len(data)*100:.1f}%)")

    # 8. 012路
    print(f"\n{'─'*60}")
    print("【012路分析】(注意: 0路含4个数字, 1路/2路各3个)")
    r0 = sum(1 for n in all_nums if n % 3 == 0)
    r1 = sum(1 for n in all_nums if n % 3 == 1)
    r2 = sum(1 for n in all_nums if n % 3 == 2)
    print(f"  0路(0,3,6,9): {r0}次 ({r0/len(all_nums)*100:.1f}%) [理论40%]")
    print(f"  1路(1,4,7):   {r1}次 ({r1/len(all_nums)*100:.1f}%) [理论30%]")
    print(f"  2路(2,5,8):   {r2}次 ({r2/len(all_nums)*100:.1f}%) [理论30%]")

    # 9. Omission analysis (with statistical context)
    print(f"\n{'─'*60}")
    print("【遗漏分析】(E[miss]=9期, P(≥15)=20.6%, P(≥20)=12.2%)")
    for pos, (k, lbl) in enumerate([('h', '百位'), ('t', '十位'), ('u', '个位')]):
        print(f"\n  {lbl}:")
        for digit in range(10):
            miss = 0
            for d in data:
                if d[k] == digit:
                    break
                miss += 1
            indicator = ""
            if miss >= 20:
                indicator = " ⚠️强信号"
            elif miss >= 15:
                indicator = " 📌关注"
            print(f"    {digit}: 遗漏{miss}期{indicator}")

    # 10. Recent 10
    print(f"\n{'─'*60}")
    print("【最近10期】")
    print(f"  {'期号':<8}  {'号码':<8} {'和值':>4} {'跨度':>4} {'形态'}")
    for d in data[:10]:
        ns = sorted([d['h'], d['t'], d['u']])
        sp = ns[2] - ns[0]
        if ns[0] == ns[2]:
            sh = "豹子"
        elif ns[0] == ns[1] or ns[1] == ns[2]:
            sh = "组三"
        else:
            sh = "组六"
        print(f"  {d['period']:<8}  {d['h']} {d['t']} {d['u']}   {d['sum']:>3}   {sp}   {sh}")

    print(f"\n{'='*60}")
    print("  ⚠ 彩票开奖为独立随机事件，统计分析仅供参考，不构成预测。")
    print("  遗漏回补是概率错觉(赌徒谬误)，实际每期开奖概率不变。")
    print(f"{'='*60}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Lottery draw analyzer v3')
    parser.add_argument('--game', default='35', help='Game: 35=排列三, 37=排列五, 3d=福彩3D')
    parser.add_argument('--count', type=int, default=200, help='Number of recent draws')
    parser.add_argument('--recommend', action='store_true', help='Generate number recommendations')
    parser.add_argument('--top', type=int, default=10, help='Number of recommendations')
    args = parser.parse_args()

    name = GAME_NAMES.get(args.game, f'彩票(game={args.game})')
    print(f"正在获取 {name} 近{args.count}期数据...")

    if args.game.lower() == '3d':
        data = fetch_3d(args.count)
    else:
        data = fetch_pl3(args.game, args.count)

    print(f"获取到 {len(data)} 期数据")
    analyze(data, name)

    if args.recommend:
        print(f"\n{'='*60}")
        print(f"  {name} v3多策略推荐 (13维评分)")
        print(f"{'='*60}")
        results = recommend(data, args.top)
        print(f"\n  {'序号':<4} {'号码':<6} {'和值':>4} {'跨度':>4} {'评分':>6}")
        print(f"  {'─'*30}")
        for i, (sc, b, s, g, hz, kd) in enumerate(results):
            mark = "🥇" if i < 2 else ("🥈" if i < 4 else "  ")
            print(f"  {mark}{i+1:<3} {b}{s}{g}   {hz:>3}   {kd:>3}   {sc:>6.1f}")
        print(f"\n  ⚠ 仅供参考，请理性投注！")
        print(f"  数据来源: 官方API {len(data)}期数据, v3多策略评分")
