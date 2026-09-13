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
from itertools import combinations
from datetime import datetime

GAME_NAMES = {
    '35': '排列三',
    '85': '大乐透',

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
    """Fetch 排列三 from sporttery official API.

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


def fetch_dlt(count=200):
    """Fetch 大乐透 from sporttery official API (gameNo=85).

    MUST use curl — sporttery.cn WAF blocks urllib with 403.
    Uses mobile UA + mobile Referer for reliable WAF bypass.
    Returns list of dicts with: period, date, front (sorted list of 5), back (sorted list of 2).
    """
    current_prefix = _get_current_year_prefix()
    all_results = []
    seen_periods = set()
    pages_needed = (count + 99) // 100

    for page in range(1, pages_needed + 1):
        url = (
            f'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry'
            f'?gameNo=85&provinceId=0&pageSize=100&isVerify=1&pageNo={page}'
        )
        result = subprocess.run([
            'curl', '-s', '-k', '--max-time', '15', url,
            '-H', f'User-Agent: {MOBILE_UA}',
            '-H', 'Accept: application/json',
            '-H', 'Referer: https://m.lottery.gov.cn/',
        ], capture_output=True, text=True, timeout=20)

        raw = result.stdout
        # 大乐透 result format: "03 04 07 12 32 01 02" (5 front + 2 back)
        nums_list = re.findall(r'"lotteryDrawResult":"(\d+ \d+ \d+ \d+ \d+ \d+ \d+)"', raw)
        periods = re.findall(r'"lotteryDrawNum":"(\d+)"', raw)
        dates = re.findall(r'"lotteryDrawTime":"(\d{4}-\d{2}-\d{2})"', raw)

        page_results = []
        for i in range(min(len(nums_list), len(periods))):
            p = periods[i]
            if p in seen_periods:
                continue
            seen_periods.add(p)

            if not p.startswith(current_prefix):
                continue

            ns = list(map(int, nums_list[i].split()))
            front = sorted(ns[:5])
            back = sorted(ns[5:7])
            d = dates[i] if i < len(dates) else ''
            page_results.append({
                'period': p,
                'date': d,
                'front': front,
                'back': back,
                'front_sum': sum(front),
                'back_sum': sum(back),
            })

        all_results.extend(page_results)

        if page < pages_needed:
            time.sleep(3)

    if not all_results:
        raise RuntimeError(
            "sporttery.cn returned no 大乐透 data — WAF may have blocked the request. "
            "Retry with mobile UA or wait a few seconds."
        )

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


def analyze_3d(data, name):
    """Run full statistical analysis for 3-digit games (3D/排列三)."""
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


# ══════════════════════════════════════════════════════════════
#  大乐透 (DLT) Analysis System — 15-dimension scoring
# ══════════════════════════════════════════════════════════════
# 前区: 1-35 选5, 后区: 1-12 选2
# 统计学基础:
#   前区单个号码出现概率 p=5/35=1/7≈14.3%
#   后区单个号码出现概率 p=2/12=1/6≈16.7%
#   前区遗漏期望 E[miss] = 1/p - 1 = 6 期
#   后区遗漏期望 E[miss] = 1/p - 1 = 5 期
#   前区和值期望 E[sum] = 5×18 = 90 (均值18)
#   后区和值期望 E[sum] = 2×6.5 = 13
# ══════════════════════════════════════════════════════════════

FRONT_RANGE = range(1, 36)   # 1-35
BACK_RANGE = range(1, 13)    # 1-12


def compute_dlt_context(data):
    """Compute all statistical context for DLT draw data.

    data: list of dicts with 'front'(sorted list of5), 'back'(sorted list of2), newest first.

    Mathematical basis:
    - Front zone (1-35): P(specific number appears) = C(34,4)/C(35,5) = 5/35 = 1/7
    - Back zone (1-12): P(specific number appears) = C(11,1)/C(12,2) = 2/12 = 1/6
    - Front miss follows Geom(1/7): E=6, σ=√(6/7)×7≈6.5
    - Back miss follows Geom(1/6): E=5, σ=√(5/6)×6≈5.5
    - Front sum: E=90, σ≈22.7 (hypergeometric approximation)
    - Back sum: E=13, σ≈4.1
    """
    ctx = {}
    n = len(data)

    # ── 前区统计 ──
    # 1. 号码频率 (近20/50/100期)
    ctx['front_freq20'] = Counter()
    ctx['front_freq50'] = Counter()
    ctx['front_freq100'] = Counter()
    for d in data[:20]:
        for x in d['front']:
            ctx['front_freq20'][x] += 1
    for d in data[:50]:
        for x in d['front']:
            ctx['front_freq50'][x] += 1
    for d in data[:100]:
        for x in d['front']:
            ctx['front_freq100'][x] += 1

    # 2. 加权热度: 近20期=5x, 20-50期=3x, 50-100期=1x
    ctx['front_weighted'] = Counter()
    for d in data[:20]:
        for x in d['front']:
            ctx['front_weighted'][x] += 5
    for d in data[20:50]:
        for x in d['front']:
            ctx['front_weighted'][x] += 3
    for d in data[50:100]:
        for x in d['front']:
            ctx['front_weighted'][x] += 1

    # 3. 遗漏值 (期数 since last appearance)
    ctx['front_miss'] = {}
    for num in FRONT_RANGE:
        for i, d in enumerate(data):
            if num in d['front']:
                ctx['front_miss'][num] = i
                break
        else:
            ctx['front_miss'][num] = n

    # 4. 位置频率 (前区5个位置)
    ctx['front_pos_freq'] = [Counter() for _ in range(5)]
    for d in data[:50]:
        for pos, num in enumerate(d['front']):
            ctx['front_pos_freq'][pos][num] += 1

    # ── 后区统计 ──
    # 5. 后区频率
    ctx['back_freq20'] = Counter()
    ctx['back_freq50'] = Counter()
    ctx['back_weighted'] = Counter()
    for d in data[:20]:
        for x in d['back']:
            ctx['back_freq20'][x] += 1
    for d in data[:50]:
        for x in d['back']:
            ctx['back_freq50'][x] += 1
    for d in data[:20]:
        for x in d['back']:
            ctx['back_weighted'][x] += 5
    for d in data[20:50]:
        for x in d['back']:
            ctx['back_weighted'][x] += 3

    # 6. 后区遗漏
    ctx['back_miss'] = {}
    for num in BACK_RANGE:
        for i, d in enumerate(data):
            if num in d['back']:
                ctx['back_miss'][num] = i
                break
        else:
            ctx['back_miss'][num] = n

    # 7. 前区和值统计
    front_sums = [d['front_sum'] for d in data]
    ctx['front_sum_avg'] = sum(front_sums[:100]) / min(100, n)
    ctx['front_sum_std'] = (sum((s - ctx['front_sum_avg'])**2
                               for s in front_sums[:100]) / min(100, n)) ** 0.5

    # 8. 后区和值统计
    back_sums = [d['back_sum'] for d in data]
    ctx['back_sum_avg'] = sum(back_sums[:100]) / min(100, n)
    ctx['back_sum_std'] = (sum((s - ctx['back_sum_avg'])**2
                              for s in back_sums[:100]) / min(100, n)) ** 0.5

    # 9. 前区跨度(最大-最小)
    front_spans = [max(d['front']) - min(d['front']) for d in data[:50]]
    ctx['front_span_avg'] = sum(front_spans) / len(front_spans)
    ctx['front_span_freq'] = Counter(front_spans)

    # 10. 奇偶比统计
    ctx['odd_even_dist'] = Counter()
    for d in data[:50]:
        odd_cnt = sum(1 for x in d['front'] if x % 2 == 1)
        ctx['odd_even_dist'][odd_cnt] += 1  # 0-5 odd numbers

    # 11. 大小比统计 (前区: 1-17小, 18-35大)
    ctx['big_small_dist'] = Counter()
    for d in data[:50]:
        big_cnt = sum(1 for x in d['front'] if x >= 18)
        ctx['big_small_dist'][big_cnt] += 1

    # 12. 三区分布 (前区: 1-12, 13-24, 25-35)
    ctx['zone_dist'] = Counter()
    for d in data[:50]:
        z1 = sum(1 for x in d['front'] if 1 <= x <= 12)
        z2 = sum(1 for x in d['front'] if 13 <= x <= 24)
        z3 = sum(1 for x in d['front'] if 25 <= x <= 35)
        ctx['zone_dist'][(z1, z2, z3)] += 1

    # 13. 邻号出现率 (上期号码在下期出现的比率)
    ctx['adjacent_rate'] = 0
    adj_total = 0
    for i in range(min(50, n - 1)):
        curr = set(data[i]['front'])
        prev = set(data[i + 1]['front'])
        overlap = curr & prev
        ctx['adjacent_rate'] += len(overlap)
        adj_total += 1
    ctx['adjacent_rate'] = ctx['adjacent_rate'] / max(adj_total, 1)

    # 14. 前区连号出现率 (相邻数字)
    ctx['consec_rate'] = 0
    for d in data[:50]:
        nums = sorted(d['front'])
        for j in range(len(nums) - 1):
            if nums[j + 1] - nums[j] == 1:
                ctx['consec_rate'] += 1
                break
    ctx['consec_rate'] = ctx['consec_rate'] / min(50, n)

    # 15. 重复号码 (相邻两期重复出现的号码)
    ctx['repeat_nums'] = Counter()
    for i in range(min(50, n - 1)):
        curr = set(data[i]['front'])
        prev = set(data[i + 1]['front'])
        for x in curr & prev:
            ctx['repeat_nums'][x] += 1

    # 16. 尾数(个位)频率
    ctx['tail_freq'] = Counter()
    for d in data[:50]:
        for x in d['front']:
            ctx['tail_freq'][x % 10] += 1

    # 17. 质合比 (质数: 2,3,5,7,11,13,17,19,23,29,31; 合数: 其余)
    primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31}
    ctx['prime_composite_dist'] = Counter()
    for d in data[:50]:
        prime_cnt = sum(1 for x in d['front'] if x in primes)
        ctx['prime_composite_dist'][prime_cnt] += 1

    return ctx


def score_dlt_front(num, pos, ctx):
    """Score a single front-zone number at a specific position.

    Dimensions:
    1. Weighted heat (recency-weighted frequency)
    2. Position-specific frequency
    3. Omission backfill (geometric distribution based)
    4. 012路 (mod3 grouping)
    5. Tail number frequency
    """
    score = 0.0

    # 1. Weighted heat
    score += ctx['front_weighted'].get(num, 0) * 0.15

    # 2. Position frequency (近50期)
    score += ctx['front_pos_freq'][pos].get(num, 0) * 1.5

    # 3. Omission backfill
    miss = ctx['front_miss'].get(num, 0)
    # P(miss >= 10) = (6/7)^10 ≈ 21.4% (notable)
    # P(miss >= 15) = (6/7)^15 ≈ 10.3% (strong)
    # P(miss >= 20) = (6/7)^20 ≈ 4.6% (extreme)
    if miss >= 10:
        score += min(miss, 25) * 0.4
    if miss >= 15:
        score += 5
    if miss >= 20:
        score += 4

    # 4. 012路
    r = num % 3
    road_cnt = sum(1 for n in range(1, 36) if n % 3 == r)
    # 0路: 12个(3,6,9,...,33,36→实际1,4,7,...,34=12个), 1路:12个, 2路:11个
    # 简化: 直接用近20期频率
    road_freq = sum(1 for d in (ctx.get('_data', [])[:20])
                    for x in d['front'] if x % 3 == r) if ctx.get('_data') else 0
    score += road_freq * 0.3

    # 5. Tail number
    tail = num % 10
    score += ctx['tail_freq'].get(tail, 0) * 0.2

    return score


def score_dlt_combo(front, back, ctx):
    """Score a complete DLT combination (5 front + 2 back).

    15 dimensions for front, 8 dimensions for back.

    Scoring philosophy:
    - Individual number quality (heat, omission, position)
    - Combination balance (odd/even, big/small, zone distribution)
    - Sum reasonableness (within 1.5σ of mean)
    - Span, consecutive, adjacency patterns
    """
    score = 0.0
    front_sorted = sorted(front)
    back_sorted = sorted(back)

    # ═══ 前区评分 ═══

    # D1: Individual number weighted heat
    for i, num in enumerate(front_sorted):
        score += ctx['front_weighted'].get(num, 0) * 0.12

    # D2: Position-specific frequency
    for i, num in enumerate(front_sorted):
        score += ctx['front_pos_freq'][i].get(num, 0) * 1.2

    # D3: Omission backfill (per number)
    for num in front_sorted:
        miss = ctx['front_miss'].get(num, 0)
        if miss >= 10:
            score += min(miss, 25) * 0.35
        if miss >= 15:
            score += 4
        if miss >= 20:
            score += 3

    # D4: Sum reasonableness (E=90, σ≈22.7)
    fsum = sum(front_sorted)
    sum_diff = abs(fsum - ctx['front_sum_avg'])
    if sum_diff <= 10:
        score += 10
    elif sum_diff <= 20:
        score += 6
    elif sum_diff <= 30:
        score += 2

    # D5: Span reasonableness
    fspan = front_sorted[-1] - front_sorted[0]
    span_diff = abs(fspan - ctx['front_span_avg'])
    if span_diff <= 5:
        score += 5
    elif span_diff <= 10:
        score += 2

    # D6: Odd/Even balance (理论最常见: 2奇3偶 or 3奇2偶)
    odd_cnt = sum(1 for x in front_sorted if x % 2 == 1)
    if odd_cnt in [2, 3]:
        score += 5
    elif odd_cnt in [1, 4]:
        score += 2
    score += ctx['odd_even_dist'].get(odd_cnt, 0) * 0.3

    # D7: Big/Small balance (1-17小, 18-35大; 理论最常见: 2大3小 or 3大2小)
    big_cnt = sum(1 for x in front_sorted if x >= 18)
    if big_cnt in [2, 3]:
        score += 5
    elif big_cnt in [1, 4]:
        score += 2
    score += ctx['big_small_dist'].get(big_cnt, 0) * 0.3

    # D8: Zone distribution (1-12, 13-24, 25-35)
    z1 = sum(1 for x in front_sorted if 1 <= x <= 12)
    z2 = sum(1 for x in front_sorted if 13 <= x <= 24)
    z3 = sum(1 for x in front_sorted if 25 <= x <= 35)
    zone_tuple = (z1, z2, z3)
    score += ctx['zone_dist'].get(zone_tuple, 0) * 0.5
    # 空区惩罚 (某区0个)
    if z1 == 0 or z2 == 0 or z3 == 0:
        score -= 3

    # D9: Consecutive numbers (连号出现率约44%)
    has_consec = any(front_sorted[i+1] - front_sorted[i] == 1
                     for i in range(4))
    if has_consec:
        score += 4

    # D10: Adjacent numbers from last draw
    if ctx.get('_data') and len(ctx['_data']) > 0:
        last_front = set(ctx['_data'][0]['front'])
        overlap = set(front_sorted) & last_front
        n_adj = len(overlap)
        # 理论期望: 5×5/35≈0.71, 实际观测约0-2
        if 1 <= n_adj <= 2:
            score += 3
        elif n_adj == 0:
            score += 1  # 也合理

    # D11: Prime/Composite balance
    primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31}
    prime_cnt = sum(1 for x in front_sorted if x in primes)
    score += ctx['prime_composite_dist'].get(prime_cnt, 0) * 0.3

    # D12: Tail number diversity
    tails = set(x % 10 for x in front_sorted)
    score += len(tails) * 1.5  # 尾数越分散越好

    # D13: Front 012路 balance
    roads = [x % 3 for x in front_sorted]
    road_counts = [roads.count(r) for r in range(3)]
    # 理论: 0路≈1.67, 1路≈1.67, 2路≈1.67
    road_balance = min(road_counts)
    score += road_balance * 2

    # ═══ 后区评分 ═══

    # D14: Individual back number quality
    for num in back_sorted:
        score += ctx['back_weighted'].get(num, 0) * 0.15

    # D15: Back omission
    for num in back_sorted:
        miss = ctx['back_miss'].get(num, 0)
        if miss >= 8:
            score += min(miss, 20) * 0.4
        if miss >= 12:
            score += 3

    # D16: Back sum reasonableness (E=13, σ≈4.1)
    bsum = sum(back_sorted)
    back_sum_diff = abs(bsum - ctx['back_sum_avg'])
    if back_sum_diff <= 2:
        score += 5
    elif back_sum_diff <= 4:
        score += 3

    # D17: Back odd/even
    back_odd = sum(1 for x in back_sorted if x % 2 == 1)
    if back_odd == 1:  # 一奇一偶最常见
        score += 3

    # D18: Back span (1奇1偶, 差值适中)
    back_span = back_sorted[1] - back_sorted[0]
    if 2 <= back_span <= 6:
        score += 2

    # D19: 冷号回补 — 组合中包含多个冷号加分
    cold_count = sum(1 for x in front_sorted
                     if ctx['front_miss'].get(x, 0) >= 12)
    if cold_count >= 2:
        score += 3

    # D20: 热号延续 — 组合中包含多个热号
    hot_front = set(x[0] for x in ctx['front_freq20'].most_common(10))
    hot_count = sum(1 for x in front_sorted if x in hot_front)
    score += hot_count * 1.5

    return score


def generate_dlt_candidates(ctx, data):
    """Generate diverse DLT candidates from10 independent strategies.

    Front zone (1-35, pick5): generates sets of5 numbers
    Back zone (1-12, pick2): generates sets of2 numbers
    Returns: list of (front_set, back_set) tuples
    """
    front_candidates = set()
    back_candidates = set()

    # ── 前区策略 ──

    # Strategy 1: Frequency hot (近20期 top 12)
    hot12 = [x[0] for x in ctx['front_freq20'].most_common(12)]
    for combo in combinations(hot12, 5):
        front_candidates.add(tuple(sorted(combo)))

    # Strategy 2: Weighted heat top 15
    heat15 = [x[0] for x in ctx['front_weighted'].most_common(15)]
    for combo in combinations(heat15, 5):
        front_candidates.add(tuple(sorted(combo)))

    # Strategy 3: Omission backfill (遗漏≥10期)
    cold_front = sorted(ctx['front_miss'].items(), key=lambda x: -x[1])
    cold_nums = [n for n, m in cold_front if m >= 10][:8]
    hot_nums = [x[0] for x in ctx['front_weighted'].most_common(10)]
    for c in cold_nums:
        pool = [x for x in hot_nums if x != c]
        if len(pool) >= 4:
            for combo in combinations(pool[:6], 4):
                front_candidates.add(tuple(sorted(combo + (c,))))

    # Strategy 4: Sum-targeted (E ± 15)
    target_sum = int(ctx['front_sum_avg'])
    for _ in range(200):
        combo = tuple(sorted(random.sample(range(1, 36), 5)))
        if abs(sum(combo) - target_sum) <= 15:
            front_candidates.add(combo)

    # Strategy 5: Zone-balanced (三区各至少1个)
    for _ in range(200):
        z1 = random.sample(range(1, 13), random.randint(1, 3))
        z2 = random.sample(range(13, 25), random.randint(1, 3))
        z3 = random.sample(range(25, 36), random.randint(1, 2))
        combo = tuple(sorted((z1 + z2 + z3)[:5]))
        if len(combo) == 5 and len(set(combo)) == 5:
            front_candidates.add(combo)

    # Strategy 6: Odd/Even balanced (2:3 or 3:2)
    odd_nums = [n for n in range(1, 36) if n % 2 == 1]
    even_nums = [n for n in range(1, 36) if n % 2 == 0]
    for _ in range(150):
        n_odd = random.choice([2, 3])
        n_even = 5 - n_odd
        combo = tuple(sorted(
            random.sample(odd_nums, n_odd) + random.sample(even_nums, n_even)
        ))
        front_candidates.add(combo)

    # Strategy 7: Last-draw adjacent (上期号码延续)
    if data:
        last_front = data[0]['front']
        for i in range(len(last_front)):
            pool = [x for x in last_front if x != last_front[i]]
            # 保留4个+补1个新的
            for new_num in range(1, 36):
                if new_num not in last_front:
                    combo = tuple(sorted(pool + [new_num]))
                    if len(combo) == 5:
                        front_candidates.add(combo)
                    if len(front_candidates) > 5000:
                        break

    # Strategy 8: Consecutive number combos (连号)
    for start in range(1, 32):
        consec_pair = (start, start + 1)
        pool = [x for x in hot12 if x not in consec_pair]
        if len(pool) >= 3:
            for combo in combinations(pool[:5], 3):
                front_candidates.add(tuple(sorted(consec_pair + combo)))

    # Strategy 9: Tail-number diverse
    for _ in range(200):
        tails = random.sample(range(10), 5)
        combo = []
        for t in tails:
            nums_with_tail = [n for n in range(1, 36)
                              if n % 10 == t and n not in combo]
            if nums_with_tail:
                combo.append(random.choice(nums_with_tail))
        if len(combo) == 5:
            front_candidates.add(tuple(sorted(combo)))

    # Strategy 10: Prime-heavy combos
    primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31]
    non_primes = [n for n in range(1, 36) if n not in set(primes)]
    for _ in range(100):
        n_prime = random.choice([2, 3])
        combo = tuple(sorted(
            random.sample(primes, n_prime) +
            random.sample(non_primes, 5 - n_prime)
        ))
        if len(combo) == 5:
            front_candidates.add(combo)

    # ── 后区策略 ──

    # Strategy 1: Hot back numbers
    hot_back = [x[0] for x in ctx['back_freq20'].most_common(6)]
    for combo in combinations(hot_back, 2):
        back_candidates.add(tuple(sorted(combo)))

    # Strategy 2: Weighted back
    heat_back = [x[0] for x in ctx['back_weighted'].most_common(8)]
    for combo in combinations(heat_back, 2):
        back_candidates.add(tuple(sorted(combo)))

    # Strategy 3: Cold back (遗漏≥6期)
    cold_back = [n for n, m in ctx['back_miss'].items() if m >= 6]
    for c in cold_back:
        for h in hot_back:
            if h != c:
                back_candidates.add(tuple(sorted([c, h])))

    # Strategy 4: Random balanced
    for _ in range(100):
        combo = tuple(sorted(random.sample(range(1, 13), 2)))
        back_candidates.add(combo)

    # Strategy 5: Odd/Even back (1奇1偶)
    odd_back = [n for n in range(1, 13) if n % 2 == 1]
    even_back = [n for n in range(1, 13) if n % 2 == 0]
    for _ in range(50):
        combo = tuple(sorted([
            random.choice(odd_back), random.choice(even_back)
        ]))
        back_candidates.add(combo)

    # Strategy 6: Last-draw back continuation
    if data:
        last_back = data[0]['back']
        for num in last_back:
            for other in range(1, 13):
                if other != num:
                    back_candidates.add(tuple(sorted([num, other])))

    return list(front_candidates), list(back_candidates)


def recommend_dlt(data, top_n=5):
    """Run DLT multi-strategy scoring and return top N DIVERSE recommendations.

    Uses diversity filtering: no two recommendations share more than 3 front numbers.
    Returns: list of (score, front_sorted, back_sorted, front_sum, back_sum)
    """
    ctx = compute_dlt_context(data)
    ctx['_data'] = data  # for adjacency checks

    front_cands, back_cands = generate_dlt_candidates(ctx, data)

    # Pre-filter: only keep front candidates with reasonable sum
    target_sum = ctx['front_sum_avg']
    sigma = ctx['front_sum_std']
    front_filtered = [f for f in front_cands
                      if abs(sum(f) - target_sum) <= 2 * sigma]

    if len(front_filtered) < 50:
        front_filtered = front_cands  # fallback

    # Score all combinations (front × back)
    # To keep computation manageable: score top 500 front × all back
    front_scored = []
    for f in front_filtered:
        sc = score_dlt_combo(f, (1, 2), ctx)  # dummy back for front scoring
        front_scored.append((sc, f))
    front_scored.sort(key=lambda x: -x[0])
    top_front = [f for _, f in front_scored[:500]]

    # Now score full combos
    all_scored = []
    for f in top_front:
        for b in back_cands:
            sc = score_dlt_combo(f, b, ctx)
            all_scored.append((sc, list(f), list(b), sum(f), sum(b)))

    all_scored.sort(key=lambda x: -x[0])

    # Diversity filtering: no two results share >3 front numbers or same back
    results = []
    for sc, front, back, fsum, bsum in all_scored:
        front_set = set(front)
        back_tuple = tuple(sorted(back))
        is_diverse = True
        for _, prev_front, prev_back, _, _ in results:
            # Front diversity: max 3 shared numbers
            overlap = len(front_set & set(prev_front))
            if overlap > 3:
                is_diverse = False
                break
            # Back diversity: no identical back pair
            if tuple(sorted(prev_back)) == back_tuple:
                is_diverse = False
                break
        if is_diverse:
            results.append((sc, front, back, fsum, bsum))
        if len(results) >= top_n:
            break

    return results


def analyze_dlt(data, name):
    """Run full statistical analysis for 大乐透."""
    print(f"\n{'='*60}")
    print(f"  {name} 近{len(data)}期数据分析报告")
    print(f"  {data[-1]['period']} ~ {data[0]['period']} ({data[-1]['date']} ~ {data[0]['date']})")
    print(f"{'='*60}")

    # ── 前区分析 ──
    print(f"\n{'─'*60}")
    print("【前区号码频率】(1-35, 理论出现率=14.3%/号/期)")
    front_counter = Counter()
    for d in data:
        for x in d['front']:
            front_counter[x] += 1

    # 按"每期出现率"计算: 出现次数/期数×100
    n_draws = len(data)
    for i in range(1, 36):
        c = front_counter.get(i, 0)
        pct = c / n_draws * 100  # 每期出现率
        expected_pct = 100 / 7  # 14.28%
        deviation = pct - expected_pct
        bar = '█' * int(pct)
        marker = '↑' if deviation > 5 else ('↓' if deviation < -5 else '')
        print(f"  {i:2d}: {c:3d}期 ({pct:5.1f}%) {bar} {marker}")

    sorted_front = sorted(front_counter.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  热号(前10): {', '.join(f'{x[0]:02d}' for x in sorted_front[:10])}")
    print(f"  冷号(后10): {', '.join(f'{x[0]:02d}' for x in sorted_front[-10:])}")

    # ── 后区分析 ──
    print(f"\n{'─'*60}")
    print("【后区号码频率】(1-12, 理论出现率=16.7%/号/期)")
    back_counter = Counter()
    for d in data:
        for x in d['back']:
            back_counter[x] += 1

    for i in range(1, 13):
        c = back_counter.get(i, 0)
        pct = c / n_draws * 100  # 每期出现率
        expected_pct = 100 / 6  # 16.67%
        deviation = pct - expected_pct
        bar = '█' * int(pct)
        marker = '↑' if deviation > 8 else ('↓' if deviation < -8 else '')
        print(f"  {i:2d}: {c:3d}期 ({pct:5.1f}%) {bar} {marker}")

    sorted_back = sorted(back_counter.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  热号: {', '.join(f'{x[0]:02d}' for x in sorted_back[:4])}")
    print(f"  冷号: {', '.join(f'{x[0]:02d}' for x in sorted_back[-4:])}")

    # ── 前区和值分析 ──
    print(f"\n{'─'*60}")
    print("【前区和值分析】(理论E=90)")
    front_sums = [d['front_sum'] for d in data]
    avg = sum(front_sums) / len(front_sums)
    std = (sum((s - avg)**2 for s in front_sums) / len(front_sums)) ** 0.5
    print(f"  范围: {min(front_sums)} ~ {max(front_sums)}  平均: {avg:.1f}  标准差: {std:.1f}")
    print(f"  中位: {sorted(front_sums)[len(front_sums)//2]}")

    for lo, hi, lbl in [(40, 69, '偏小'), (70, 89, '中低'), (90, 109, '中高'), (110, 140, '偏大')]:
        cnt = sum(1 for s in front_sums if lo <= s <= hi)
        pct = cnt / len(front_sums) * 100
        print(f"  {lbl}({lo:3d}-{hi:3d}): {cnt:3d}期 ({pct:5.1f}%) {'█' * int(pct / 2)}")

    # ── 后区和值分析 ──
    print(f"\n{'─'*60}")
    print("【后区和值分析】(理论E=13)")
    back_sums = [d['back_sum'] for d in data]
    bavg = sum(back_sums) / len(back_sums)
    bstd = (sum((s - bavg)**2 for s in back_sums) / len(back_sums)) ** 0.5
    print(f"  范围: {min(back_sums)} ~ {max(back_sums)}  平均: {bavg:.1f}  标准差: {bstd:.1f}")

    for lo, hi, lbl in [(3, 8, '小'), (9, 13, '中'), (14, 18, '大'), (19, 23, '超大')]:
        cnt = sum(1 for s in back_sums if lo <= s <= hi)
        pct = cnt / len(back_sums) * 100
        print(f"  {lbl}({lo:2d}-{hi:2d}): {cnt:3d}期 ({pct:5.1f}%) {'█' * int(pct / 2)}")

    # ── 奇偶比 ──
    print(f"\n{'─'*60}")
    print("【前区奇偶比】")
    oe_dist = Counter()
    for d in data[:100]:
        odd = sum(1 for x in d['front'] if x % 2 == 1)
        oe_dist[odd] += 1
    for odd_cnt in range(6):
        cnt = oe_dist.get(odd_cnt, 0)
        pct = cnt / min(100, len(data)) * 100
        label = f"{odd_cnt}奇{5-odd_cnt}偶"
        print(f"  {label}: {cnt}期 ({pct:.1f}%) {'█' * int(pct / 2)}")

    # ── 大小比 ──
    print(f"\n{'─'*60}")
    print("【前区大小比】(1-17小, 18-35大)")
    bs_dist = Counter()
    for d in data[:100]:
        big = sum(1 for x in d['front'] if x >= 18)
        bs_dist[big] += 1
    for big_cnt in range(6):
        cnt = bs_dist.get(big_cnt, 0)
        pct = cnt / min(100, len(data)) * 100
        label = f"{big_cnt}大{5-big_cnt}小"
        print(f"  {label}: {cnt}期 ({pct:.1f}%) {'█' * int(pct / 2)}")

    # ── 三区分布 ──
    print(f"\n{'─'*60}")
    print("【前区三区分布】(1-12/13-24/25-35)")
    zone_dist = Counter()
    for d in data[:100]:
        z1 = sum(1 for x in d['front'] if 1 <= x <= 12)
        z2 = sum(1 for x in d['front'] if 13 <= x <= 24)
        z3 = sum(1 for x in d['front'] if 25 <= x <= 35)
        zone_dist[(z1, z2, z3)] += 1
    top_zones = zone_dist.most_common(10)
    for (z1, z2, z3), cnt in top_zones:
        pct = cnt / min(100, len(data)) * 100
        print(f"  {z1}:{z2}:{z3} = {cnt}期 ({pct:.1f}%)")

    # ── 跨度分析 ──
    print(f"\n{'─'*60}")
    print("【前区跨度分析】(最大-最小)")
    spans = [max(d['front']) - min(d['front']) for d in data[:100]]
    span_avg = sum(spans) / len(spans)
    print(f"  平均跨度: {span_avg:.1f}")
    span_dist = Counter(spans)
    for sp in sorted(span_dist.keys()):
        cnt = span_dist[sp]
        pct = cnt / len(spans) * 100
        if pct >= 3:
            print(f"  跨度{sp:2d}: {cnt:2d}期 ({pct:.1f}%) {'█' * int(pct / 2)}")

    # ── 遗漏分析 ──
    print(f"\n{'─'*60}")
    print("【前区遗漏分析】(E[miss]=6期, P(≥10)=21.4%, P(≥15)=10.3%)")
    for num in range(1, 36):
        miss = 0
        for d in data:
            if num in d['front']:
                break
            miss += 1
        indicator = ""
        if miss >= 20:
            indicator = " ⚠️强信号"
        elif miss >= 15:
            indicator = " 📌关注"
        elif miss >= 10:
            indicator = " 🔔留意"
        if miss >= 8:
            print(f"  {num:2d}: 遗漏{miss:2d}期{indicator}")

    print(f"\n【后区遗漏分析】(E[miss]=5期, P(≥8)=23.3%, P(≥12)=11.2%)")
    for num in range(1, 13):
        miss = 0
        for d in data:
            if num in d['back']:
                break
            miss += 1
        indicator = ""
        if miss >= 12:
            indicator = " ⚠️强信号"
        elif miss >= 8:
            indicator = " 📌关注"
        elif miss >= 6:
            indicator = " 🔔留意"
        if miss >= 4:
            print(f"  {num:2d}: 遗漏{miss:2d}期{indicator}")

    # ── 最近10期 ──
    print(f"\n{'─'*60}")
    print("【最近10期】")
    print(f"  {'期号':<8} {'前区号码':<20} {'后区':<8} {'前和':>4} {'后和':>4}")
    for d in data[:10]:
        front_str = ' '.join(f'{x:02d}' for x in d['front'])
        back_str = ' '.join(f'{x:02d}' for x in d['back'])
        print(f"  {d['period']:<8} {front_str:<20} {back_str:<8} {d['front_sum']:>4} {d['back_sum']:>4}")

    print(f"\n{'='*60}")
    print("  ⚠ 彩票开奖为独立随机事件，统计分析仅供参考，不构成预测。")
    print("  大乐透前区C(35,5)=324632, 后区C(12,2)=66, 总组合=21,425,712。")
    print("  任何分析方法都无法改变每注等概率的基本事实。")
    print(f"{'='*60}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Lottery draw analyzer v3')
    parser.add_argument('--game', default='35', help='Game: 35=排列三, 85=大乐透, 3d=福彩3D')
    parser.add_argument('--count', type=int, default=200, help='Number of recent draws')
    parser.add_argument('--recommend', action='store_true', help='Generate number recommendations')
    parser.add_argument('--top', type=int, default=10, help='Number of recommendations')
    args = parser.parse_args()

    name = GAME_NAMES.get(args.game, f'彩票(game={args.game})')
    print(f"正在获取 {name} 近{args.count}期数据...")

    if args.game.lower() == '3d':
        data = fetch_3d(args.count)
    elif args.game == '85':
        data = fetch_dlt(args.count)
    else:
        data = fetch_pl3(args.game, args.count)

    print(f"获取到 {len(data)} 期数据")

    if args.game == '85':
        analyze_dlt(data, name)
    else:
        analyze_3d(data, name)

    if args.recommend:
        print(f"\n{'='*60}")
        if args.game == '85':
            print(f"  {name} v3多策略推荐 (20维评分)")
            print(f"{'='*60}")
            results = recommend_dlt(data, args.top)
            print(f"\n  {'序号':<4} {'前区号码':<20} {'后区':<8} {'前和':>4} {'后和':>4} {'评分':>6}")
            print(f"  {'─'*55}")
            for i, (sc, front, back, fsum, bsum) in enumerate(results):
                front_str = ' '.join(f'{x:02d}' for x in sorted(front))
                back_str = ' '.join(f'{x:02d}' for x in sorted(back))
                mark = "🥇" if i < 1 else ("🥈" if i < 2 else ("🥉" if i < 3 else "  "))
                print(f"  {mark}{i+1:<3} {front_str:<20} {back_str:<8} {fsum:>4} {bsum:>4} {sc:>6.1f}")
        else:
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
