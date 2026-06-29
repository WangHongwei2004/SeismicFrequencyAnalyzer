from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np


# ── 常量 ────────────────────────────────────────────────────────

_BLOCK_SIZE = 50          # 每分量每块 50 个 int32
_GAP_SIZE = 1             # 每 3 块后 1 个间隙
_CYCLE_SIZE = _BLOCK_SIZE * 3 + _GAP_SIZE  # 151


# ── 数据类 ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class EvtHeader:
    station_id: int
    station_name: str
    instrument: str
    latitude: float
    longitude: float
    elevation_m: float
    record_time: datetime | None
    preamble_int32: int     # 第一个 UD 块在 int32 流中的偏移
    total_frames: int       # 每分量有效样本数


@dataclass(frozen=True)
class EvtData:
    header: EvtHeader
    ew: np.ndarray
    ns: np.ndarray
    ud: np.ndarray

    @property
    def sample_count(self) -> int:
        return int(self.ew.size)


# ── 公共 API ────────────────────────────────────────────────────

def read_evt(file_path: str | Path) -> EvtData:
    file_path = Path(file_path)
    data = np.fromfile(file_path, dtype=np.uint8)

    if b"digital event" not in data[:16].tobytes():
        raise ValueError(f"不是有效的 EVT 文件: {file_path}")

    station_id = int(struct.unpack_from("<I", data, 0x100)[0])
    fmt_flag   = int(struct.unpack_from("<H", data, 0x10A)[0])

    record_time = _parse_evt_time(
        int(struct.unpack_from("<H", data, 0x10C)[0]),
        int(struct.unpack_from("<H", data, 0x10E)[0]),
        int(struct.unpack_from("<H", data, 0x110)[0]),
        int(struct.unpack_from("<H", data, 0x112)[0]),
        int(struct.unpack_from("<H", data, 0x114)[0]),
        int(struct.unpack_from("<H", data, 0x116)[0]),
        file_path,
    )

    station_name = _clean_str(data[0x11C:0x11C + 16].tobytes())
    instrument   = _clean_str(data[0x12C:0x12C + 16].tobytes())
    latitude     = float(struct.unpack_from("<f", data, 0x7C)[0])
    longitude    = float(struct.unpack_from("<f", data, 0x80)[0])
    elevation_m  = float(struct.unpack_from("<f", data, 0x84)[0])

    # ── 数据区 ──
    dstart = _find_data_start(data)
    raw = data[dstart:]
    n_int32 = len(raw) // 4
    arr = raw[:n_int32 * 4].view(np.int32)

    preamble = _find_preamble(arr)
    body = arr[preamble:]
    total_cycles = len(body) // _CYCLE_SIZE
    total_per_comp = total_cycles * _BLOCK_SIZE

    ew = np.zeros(total_per_comp, dtype=np.float64)
    ns = np.zeros(total_per_comp, dtype=np.float64)
    ud = np.zeros(total_per_comp, dtype=np.float64)

    for cyc in range(total_cycles):
        base = cyc * _CYCLE_SIZE
        off = cyc * _BLOCK_SIZE
        ud[off:off + _BLOCK_SIZE] = body[base + 0 * _BLOCK_SIZE:base + 1 * _BLOCK_SIZE]
        ns[off:off + _BLOCK_SIZE] = body[base + 1 * _BLOCK_SIZE:base + 2 * _BLOCK_SIZE]
        ew[off:off + _BLOCK_SIZE] = body[base + 2 * _BLOCK_SIZE:base + 3 * _BLOCK_SIZE]

    header = EvtHeader(
        station_id=station_id, station_name=station_name,
        instrument=instrument, latitude=latitude, longitude=longitude,
        elevation_m=elevation_m, record_time=record_time,
        preamble_int32=preamble, total_frames=total_per_comp,
    )

    return EvtData(header=header, ew=ew, ns=ns, ud=ud)


# ── 内部函数 ────────────────────────────────────────────────────

def _clean_str(raw: bytes) -> str:
    text = raw.rstrip(b"\x00").decode("latin-1", errors="replace")
    return "".join(ch if ch.isprintable() or ch in "\n\r\t" else " "
                   for ch in text).strip()


def _parse_evt_time(year, doy, h, m, s, ms, file_path) -> datetime | None:
    import re
    m = re.search(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", file_path.stem)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]))
        except ValueError:
            pass
    try:
        y = 2000 + year if year < 100 else year
        if 1 <= doy <= 366:
            from datetime import timedelta
            return (datetime(y, 1, 1) + timedelta(days=doy - 1)).replace(
                hour=h % 24, minute=m % 60, second=s % 60,
                microsecond=(ms % 1000) * 1000)
    except (ValueError, OverflowError):
        pass
    return None


def _find_data_start(data: np.ndarray) -> int:
    raw_bytes = data.tobytes()
    for marker in (b"E-W", b"N-S"):
        pos = raw_bytes.find(marker)
        if pos >= 4:
            seg_start = pos - 4
            n_calib = struct.unpack_from("<I", raw_bytes, seg_start + 32)[0]
            if 0 < n_calib < 50:
                return seg_start + 36 + n_calib * 8
    return 0x322C


def _find_preamble(arr: np.ndarray) -> int:
    """找到第一个 UD 块的起始 int32 索引。

    数据格式：arr 开头有一段前导，之后是规整的
    50-样本块序列 [UD×50][NS×50][EW×50][gap]。
    搜索连续 5 个合理值的位置作为起始。
    """
    for i in range(0, min(20000, len(arr) - 5)):
        vals = arr[i:i + 5].astype(np.float64)
        if np.all(np.abs(vals) > 100) and np.max(np.abs(np.diff(vals))) < 1000:
            return int(i)
    return 0


def find_first_valid_frame(evt_data: EvtData) -> int:
    return evt_data.header.preamble_int32


def get_component_array(evt_data: EvtData, component: str) -> np.ndarray:
    mapping = {"EW": evt_data.ew, "NS": evt_data.ns, "UD": evt_data.ud}
    if component not in mapping:
        raise ValueError(f"未知分量名: {component}，可选: EW, NS, UD")
    return mapping[component]