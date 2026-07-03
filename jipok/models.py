"""자료구조."""
from dataclasses import dataclass, field


@dataclass
class Order:
    idx: int            # 순서 번호(1-base)
    jeong: int          # 정길이 (m)
    kwonchwi: int       # 권취 수
    width: int          # 23호기요청지폭(표준지폭)
    bosang: int         # 보상길이


@dataclass
class Spool:
    jeong: int
    width: int          # 그룹 내 최대폭
    bosang: int         # 그룹 내 최대보상
    N: int              # 완스풀(스풀당 마끼)
    contribs: list = field(default_factory=list)  # [[order_idx, count], ...]
    yeoyu: int = 0

    @property
    def filled(self):
        return sum(c[1] for c in self.contribs) + self.yeoyu


@dataclass
class Row:
    width: int
    jeong: int
    N: int
    spools: int
    contribs: list      # [[order_idx, count], ...] 집계
    yeoyu: int
    bosang: int
    choji_real: int = 0
    saengsan: int = 0

    def bigo(self):
        parts = [f"(순서{o}번){self.jeong:,}m용*{c}회" for o, c in self.contribs]
        if self.yeoyu:
            parts.append(f"여유분 {self.yeoyu}회")
        return "+".join(parts)
