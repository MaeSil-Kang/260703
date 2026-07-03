"""스케줄러(패커) v2 — 권취를 스풀로 묶고 인접 병합/균등분할/여유분 처리.

규칙(답지 LOT 2260600339 역산, 작업자 판단 반영):
  - 각 주문은 원칙적으로 '자기 순서'로 스풀을 만든다(순번 건너뛰기 병합 금지).
  - 병합은 '바로 다음 순서(i+1)'와만, 그리고 현재 잔량이 CP중량 11에 못 미쳐
    홀로 설 수 없을 때만 한다(같은 정길이 & 폭차<=tol). → 인접 병합만 허용.
  - 권취가 완스풀 N을 넘으면 ceil(권취/N) 개 스풀로 '균등' 분할(욕심껏 N 채우기 X).
      예) 13마끼·N9 → 7+6,  21마끼·N7 → 7+7+7.
  - 모든 스풀은 CP중량 11~33. 부족분은 여유분(min_n)으로 채워 확정.
  - 같은 (폭,정길이,실채움) 스풀들을 한 행으로 집계.
  - 총생산길이는 초지공정길이 이상이 되도록 여유분으로 보충(상한은 느슨).
주의: 여유분 정밀배치는 작업자 판단 영역 → '유효하고 답지 구조에 일치'를 목표.
"""
import math
from . import calc
from . import constants as C
from .models import Order, Spool, Row

WIDTH_TOL = 20          # 병합 허용 폭차(기본). 평균이하 폭은 50.
LONG_ROLL_N = 7         # 완스풀 N이 이 값 이하인 '긴 롤'은 단독 부분스풀을 완스풀까지 채움


def _N(jeong, width, bosang, cp, teukgam):
    return calc.wanspool_N(jeong, bosang, cp, width, teukgam) or 1


def _count(sp):
    return sum(c[1] for c in sp.contribs)


def _add(sp, order_idx, n):
    if sp.contribs and sp.contribs[-1][0] == order_idx:
        sp.contribs[-1][1] += n
    else:
        sp.contribs.append([order_idx, n])


def _balanced(total, k):
    """total을 k조각으로 균등 분할. 앞쪽이 큼. 예) (13,2)->[7,6], (21,3)->[7,7,7]."""
    base, rem = divmod(total, k)
    return [base + 1 if i < rem else base for i in range(k)]


def make_spools(orders, cp, teukgam):
    """주문 리스트 -> 스풀 리스트.

    핵심(답지 학습):
      - 순번 건너뛰기 병합 금지: carry는 '바로 다음 순서'에서만 합쳐진다.
      - 작은 주문(권취<CP중량11 최소)만 인접 병합 대상. 그 외엔 자기 스풀.
      - 큰 주문은 ceil(권취/N) 스풀로 균등 분할.
    """
    spools = []
    widths = [o.width for o in orders] or [0]
    avg = (max(widths) + min(widths)) / 2

    def tol(w1, w2):
        return 50 if min(w1, w2) < avg else WIDTH_TOL

    def Nof(j, w, b):
        return _N(j, w, b, cp, teukgam)

    def minof(j, w, b):
        return calc.min_n_cp11(j, b, cp, w, teukgam)

    def finalize(s):
        """자체 스풀 확정: CP중량>=11 되도록 여유분 채움."""
        need = minof(s.jeong, s.width, s.bosang)
        if _count(s) + s.yeoyu < need:
            s.yeoyu = need - _count(s)

    carry = None   # 바로 다음 순서와만 합칠 부분스풀(<min). 절대 건너뛰지 않음.
    for i, o in enumerate(orders):
        # 1) 들어온 carry(직전 순서 잔량)와 결합 시도 — 호환되면 합치고, 아니면 단독 확정
        group = []
        gj, gw, gb = o.jeong, o.width, o.bosang
        if carry is not None:
            if carry.jeong == o.jeong and abs(carry.width - o.width) <= tol(carry.width, o.width):
                group = [list(c) for c in carry.contribs]
                gw = max(gw, carry.width)
                gb = max(gb, carry.bosang)
            else:
                finalize(carry); spools.append(carry)   # 인접 불호환 → 단독 확정
            carry = None

        _add_group(group, o.idx, o.kwonchwi)
        M = sum(c[1] for c in group)
        if M == 0:
            continue
        N = Nof(gj, gw, gb)
        mn = minof(gj, gw, gb)

        # 2) 너무 작아 홀로 설 수 없으면(권취<CP중량11) → 바로 다음 순서로만 이월
        if M < mn:
            nxt = orders[i + 1] if i + 1 < len(orders) else None
            if nxt is not None and nxt.jeong == gj and abs(gw - nxt.width) <= tol(gw, nxt.width):
                carry = Spool(gj, gw, gb, N, group, 0)
                continue
            sp = Spool(gj, gw, gb, N, group, 0)
            finalize(sp); spools.append(sp)
            continue

        # 3) 완스풀 N 기준 ceil 분할(균등). 가장 작은 조각도 CP중량11 보장.
        k = max(1, math.ceil(M / N))
        while k > 1 and (M // k) < mn:
            k -= 1
        sizes = _balanced(M, k)
        gi, gcnt = 0, group[0][1]
        for s in sizes:
            sp = Spool(gj, gw, gb, N, [], 0)
            need = s
            while need > 0:
                if gcnt == 0:
                    gi += 1
                    gcnt = group[gi][1]
                take = min(need, gcnt)
                _add(sp, group[gi][0], take)
                gcnt -= take
                need -= take
            spools.append(sp)

    if carry is not None:
        finalize(carry); spools.append(carry)
    return spools


def _add_group(group, order_idx, n):
    if group and group[-1][0] == order_idx:
        group[-1][1] += n
    else:
        group.append([order_idx, n])


def spools_to_rows(spools, cp, teukgam):
    """연속한 동일 (폭,정길이,실채움) 스풀을 한 행으로 집계.
    길이는 완스풀 N이 아니라 '실제 채운 마끼수(실채움=마끼+여유)'로 계산."""
    rows = []
    for s in spools:
        filled = _count(s) + s.yeoyu          # 실제 채운 마끼수
        key = (s.width, s.jeong, filled)
        if rows and (rows[-1].width, rows[-1].jeong, rows[-1].N) == key:
            r = rows[-1]
            r.spools += 1
            for oi, c in s.contribs:
                if r.contribs and r.contribs[-1][0] == oi:
                    r.contribs[-1][1] += c
                else:
                    r.contribs.append([oi, c])
            r.yeoyu += s.yeoyu
            r.bosang = max(r.bosang, s.bosang)
        else:
            rows.append(Row(s.width, s.jeong, filled, 1,
                            [list(c) for c in s.contribs], s.yeoyu, s.bosang))
    # 길이 계산 (r.N = 실채움)
    for r in rows:
        r.choji_real = calc.choji_saengsan_real(r.jeong, r.bosang, r.N, cp, teukgam)
        r.saengsan = calc.saengsan_len(r.jeong, r.bosang, r.N, r.spools, cp, teukgam)
    return rows


def _spool_saengsan(s, cp, teukgam):
    filled = _count(s) + s.yeoyu
    js = calc.wonji_jeonsan(s.jeong, s.bosang, filled, cp, teukgam)
    return calc.round100(js)


def topup_yeoyu(spools, cp, teukgam, choji_len, lo=1000, hi=60000):
    """총생산길이를 초지공정길이 이상으로 끌어올리는 여유분 보충(상한은 느슨).
    답지 학습: 순서1은 '필수 여유분 1회'만 받고, 추가 보충은 '넓은 폭' 부분스풀에
    우선 더한다(순서1을 완스풀까지 채우지 않음). 이미 +lo 충족이면 추가 안 함."""
    if not choji_len:
        return
    total = lambda: sum(_spool_saengsan(s, cp, teukgam) for s in spools)
    target_lo, target_hi = choji_len + lo, choji_len + hi
    o1 = spools[0].contribs[0][0] if spools and spools[0].contribs else None

    def under(s):
        return (_count(s) + s.yeoyu) < s.N

    def is_o1(s):
        return s.contribs and s.contribs[0][0] == o1

    def delta(s):
        f = _count(s) + s.yeoyu
        return calc.round100(calc.wonji_jeonsan(s.jeong, s.bosang, f + 1, cp, teukgam)) - \
               calc.round100(calc.wonji_jeonsan(s.jeong, s.bosang, f, cp, teukgam))

    # 순서1 필수 여유분(규칙4-4): 순서1 부분스풀이 있으면 1회만 채운다.
    o1_part = next((s for s in spools if is_o1(s) and under(s)), None)
    if o1_part is not None:
        o1_part.yeoyu += 1

    guard = 0
    while total() < target_lo and guard < 2000:
        cur = total()
        # 추가 보충은 순서1 제외, 넓은 폭 부분스풀 우선
        cand = [s for s in spools if under(s) and not is_o1(s)]
        if not cand:
            cand = [s for s in spools if under(s)]   # 순서1만 남으면 부득이 사용
        if not cand:
            # 모두 꽉 참 → 새 여유 스풀 추가(가장 넓은 폭). 다음 반복에서 채워짐.
            b = max(spools, key=lambda s: s.width)
            spools.append(Spool(b.jeong, b.width, b.bosang, b.N, [], 1))
            guard += 1
            continue
        safe = [s for s in cand if cur + delta(s) <= target_hi]
        pool = safe if safe else cand
        # 규칙3-2: 넓은 폭(손율 영향 작고 권취 많은 곳) 우선, 동폭이면 긴 정길이
        pool.sort(key=lambda s: (-s.width, -s.jeong))
        pool[0].yeoyu += 1
        guard += 1


def pad_long_rolls(spools):
    """긴 롤(완스풀 N<=LONG_ROLL_N, 예 15,000m·N7) 부분스풀을 완스풀까지 여유분으로 채움.
    답지 학습: 작업자는 15,000m 같은 긴 롤을 부분으로 돌리지 않고 완스풀(N)까지 완성한다.
    단, '주문 전량이 한 스풀에 든 단독 스풀'만 대상(균등 분할된 스풀은 그대로 둠).
    topup(길이 보충) 이후에 호출 → 순서별 여유분과 별개로 긴 롤만 추가 패딩."""
    glob = {}
    for s in spools:
        for o, c in s.contribs:
            glob[o] = glob.get(o, 0) + c
    for s in spools:
        if s.N > LONG_ROLL_N or (_count(s) + s.yeoyu) >= s.N:
            continue
        orders_in = {o for o, _ in s.contribs}
        if orders_in and sum(glob[o] for o in orders_in) <= s.N:   # 단일스풀(분할 아님)
            s.yeoyu = s.N - _count(s)


def enforce_even_short(spools):
    """<10,000m(합권)은 스풀당 총 마끼(권취+여유)가 짝수여야 한다 → 홀수면 여유분 +1."""
    for s in spools:
        if s.jeong < C.SHORT_LEN and (_count(s) + s.yeoyu) % 2 == 1:
            s.yeoyu += 1


def merge_for_convenience(spools, cp, teukgam):
    """작업편리성 모드: 인접 스풀을 합쳐 스풀 수를 줄인다(완스풀 위주).
    조건: 같은 정길이 & 폭차<=tol & 합산 마끼 <= 완스풀N. **인접 스풀끼리만**(순번
    건너뛰기 없음). 손율최소 결과에 한 번 더 패스 → 멀쩡한 인접 주문도 한 스풀에 합쳐
    스풀 수↓(대신 좁은 주문이 넓은 폭으로 가 폭손실 소폭↑). topup 이전에 호출."""
    if len(spools) <= 1:
        return spools
    widths = [s.width for s in spools]
    avg = (max(widths) + min(widths)) / 2

    def tol(w1, w2):
        return 50 if min(w1, w2) < avg else WIDTH_TOL

    out = [spools[0]]
    for s in spools[1:]:
        p = out[-1]
        w = max(p.width, s.width); b = max(p.bosang, s.bosang)
        n = _N(p.jeong, w, b, cp, teukgam)
        if (p.jeong == s.jeong and abs(p.width - s.width) <= tol(p.width, s.width)
                and _count(p) + _count(s) <= n):
            p.width, p.bosang, p.N = w, b, n
            for oi, c in s.contribs:
                _add(p, oi, c)
            p.yeoyu += s.yeoyu
        else:
            out.append(s)
    return out


def schedule(orders, cp, teukgam, choji_gongjeong_len=0, mode="loss"):
    """mode='loss'(손율 최소, 기본) | 'convenience'(작업 편리성, 인접 병합으로 스풀↓)."""
    spools = make_spools(orders, cp, teukgam)
    if mode == "convenience":
        spools = merge_for_convenience(spools, cp, teukgam)
    topup_yeoyu(spools, cp, teukgam, choji_gongjeong_len)
    pad_long_rolls(spools)                 # 긴 롤(N<=7) 단독 부분스풀 완스풀 패딩
    enforce_even_short(spools)             # <10000m 합권 짝수화
    # 폭 내림차순, 동폭이면 가장 앞 순서 우선(결과가 순서 흐름대로 보이도록)
    spools.sort(key=lambda s: (-s.width, min((c[0] for c in s.contribs), default=999)))
    rows = spools_to_rows(spools, cp, teukgam)
    total = sum(r.saengsan for r in rows)
    return rows, total
