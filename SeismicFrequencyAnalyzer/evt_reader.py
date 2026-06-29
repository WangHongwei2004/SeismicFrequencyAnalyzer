# -*- coding: utf-8 -*-
"""EDAS EVT 二进制格式文件解析模块。

支持读取 EDAS-24 系列数字地震仪生成的 EVT 事件文件，
提取全局头段信息及三分量（EW/NS/UD）交织 int16 数据。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np


# ── 数据类 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvtHeader:
    """EVT 文件全局头段信息。"""

    station_id: int
    """台站 ID"""
    station_name: str
    """台站名称"""
    instrument: str
    """仪器型号"""
    latitude: float
    """纬度（度）"""
    longitude: float
    """经度（度）"""
    elevation_m: float
    """高程（米）"""
    sample_rate_hz: float
    """采样率（Hz），从数据段头中读取"""
    component_count: int
    """分量数"""
    data_format: int
    """数据格式标志（8=16-bit int）"""
    record_time: datetime | None
    """记录起始时间（若可解析）"""
    total_frames: int
    """总数据帧数（三分量交织）"""
    data_start_offset: int
    """数据区起始字节偏移"""


@dataclass(frozen=True)
class EvtData:
    """EVT 三分量数据。"""

    header: EvtHeader
    ew: np.ndarray
    """东西分量（int16）"""
    ns: np.ndarray
    """南北分量（int16）"""
    ud: np.ndarray
    """垂直分量（int16）"""

    @property
    def sample_count(self) -> int:
        return int(self.ew.size)

    @property
    def duration_s(self) -> float:
        return self.sample_count / self.header.sample_rate_hz

    @property
    def time_s(self) -> np.ndarray:
        return np.arange(self.sample_count, dtype=float) / self.header.sample_rate_hz


# ── 解析函数 ──────────────────────────────────────────────────────


def _clean_string(raw: bytes, encoding: str = "latin-1") -> str:
    """清理二进制字符串，去除尾部空白和不可打印字符。"""
    text = raw.rstrip(b"\x00").decode(encoding, errors="replace")
    return "".join(ch if ch.isprintable() or ch in "\n\r\t" else " " for ch in text).strip()


def read_evt(file_path: str | Path) -> EvtData:
    """读取 EVT 文件，返回三分量数据。

    Parameters
    ----------
    file_path : str or Path
        EVT 文件路径。

    Returns
    -------
    EvtData
        包含头信息和三分量数据的对象。
    """
    file_path = Path(file_path)
    with open(file_path, "rb") as fh:
        data = fh.read()

    file_size = len(data)

    # 验证文件魔数
    magic = data[:16]
    if b"digital event" not in magic:
        raise ValueError(f"不是有效的 EVT 文件（缺少 'digital event' 标识）: {file_path}")

    # ── 解析全局头段 ──
    station_id = struct.unpack_from("<I", data, 0x100)[0]
    data_length = struct.unpack_from("<I", data, 0x104)[0]
    component = struct.unpack_from("<H", data, 0x108)[0]
    fmt_flag = struct.unpack_from("<H", data, 0x10A)[0]

    # 时间字段（尝试多种解析方式）
    year = struct.unpack_from("<H", data, 0x10C)[0]
    day_of_year = struct.unpack_from("<H", data, 0x10E)[0]
    hour_field = struct.unpack_from("<H", data, 0x110)[0]
    minute_field = struct.unpack_from("<H", data, 0x112)[0]
    second_field = struct.unpack_from("<H", data, 0x114)[0]
    ms_field = struct.unpack_from("<H", data, 0x116)[0]

    record_time = _parse_evt_time(year, day_of_year, hour_field, minute_field,
                                   second_field, ms_field, file_path)

    # 台站名（0x11C 起 16 字节）
    station_name_raw = data[0x11C:0x11C + 16]
    station_name = _clean_string(station_name_raw, "latin-1")

    # 仪器型号（0x12C 起 16 字节）
    instrument_raw = data[0x12C:0x12C + 16]
    instrument = _clean_string(instrument_raw, "latin-1")

    # 经纬度（0x7C 起）
    latitude = struct.unpack_from("<f", data, 0x7C)[0]
    longitude = struct.unpack_from("<f", data, 0x80)[0]

    # 高程（0x84 起）
    elevation_m = struct.unpack_from("<f", data, 0x84)[0]

    # ── 查找第一个分量段头，获取采样率 ──
    sample_rate_hz = _find_sample_rate(data)

    # ── 查找数据区起始位置 ──
    data_start_offset = _find_data_start(data)

    # ── 读取三分量交织数据 ──
    total_data_bytes = file_size - data_start_offset
    n_frames = total_data_bytes // 6  # 每个分量 2 字节，3 分量 = 6 字节/帧

    ew = np.zeros(n_frames, dtype=np.int16)
    ns = np.zeros(n_frames, dtype=np.int16)
    ud = np.zeros(n_frames, dtype=np.int16)

    for i in range(n_frames):
        off = data_start_offset + i * 6
        ew[i] = struct.unpack_from("<h", data, off)[0]
        ns[i] = struct.unpack_from("<h", data, off + 2)[0]
        ud[i] = struct.unpack_from("<h", data, off + 4)[0]

    header = EvtHeader(
        station_id=station_id,
        station_name=station_name,
        instrument=instrument,
        latitude=latitude,
        longitude=longitude,
        elevation_m=elevation_m,
        sample_rate_hz=sample_rate_hz,
        component_count=3,
        data_format=fmt_flag,
        record_time=record_time,
        total_frames=n_frames,
        data_start_offset=data_start_offset,
    )

    return EvtData(header=header, ew=ew, ns=ns, ud=ud)


def _parse_evt_time(
    year: int,
    day_of_year: int,
    hour: int,
    minute: int,
    second: int,
    ms: int,
    file_path: Path,
) -> datetime | None:
    """尝试从多种可能的字段排列中解析时间。"""
    # 首先尝试从文件名中提取时间（最可靠）
    import re

    name_match = re.search(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", file_path.stem)
    if name_match:
        try:
            return datetime(
                year=int(name_match.group(1)),
                month=int(name_match.group(2)),
                day=int(name_match.group(3)),
                hour=int(name_match.group(4)),
                minute=int(name_match.group(5)),
                second=0,
            )
        except ValueError:
            pass

    # 尝试解析头字段：year 可能是 2000+year 的偏移
    actual_year = 2000 + year if year < 100 else year
    try:
        # 尝试 day_of_year 作为儒略日
        if 1 <= day_of_year <= 366:
            from datetime import timedelta
            dt = datetime(actual_year, 1, 1) + timedelta(days=day_of_year - 1)
            return dt.replace(hour=hour % 24, minute=minute % 60,
                              second=second % 60, microsecond=(ms % 1000) * 1000)
    except (ValueError, OverflowError):
        pass

    return None


def _find_sample_rate(data: bytes) -> float:
    """从分量段头中提取采样率。"""
    # 搜索 'E-W' 分量段头，其 +20 字节处为 float 采样率
    ew_pos = data.find(b"E-W")
    if ew_pos >= 4:
        seg_start = ew_pos - 4  # 段头起始
        if seg_start + 24 <= len(data):
            sr = struct.unpack_from("<f", data, seg_start + 20)[0]
            if 10.0 < sr < 10000.0:
                return sr

    # 备选：搜索 'N-S' 分量段头
    ns_pos = data.find(b"N-S")
    if ns_pos >= 4:
        seg_start = ns_pos - 4
        if seg_start + 24 <= len(data):
            sr = struct.unpack_from("<f", data, seg_start + 20)[0]
            if 10.0 < sr < 10000.0:
                return sr

    return 100.0  # 默认 100 Hz


def _find_data_start(data: bytes) -> int:
    """查找实际数据区的起始偏移。

    搜索第一个分量段头（E-W），跳过其校准数据后即为数据区起始。
    """
    ew_pos = data.find(b"E-W")
    if ew_pos >= 4:
        seg_start = ew_pos - 4
        n_calib = struct.unpack_from("<I", data, seg_start + 32)[0]
        if n_calib > 0 and n_calib < 50:
            data_start = seg_start + 36 + n_calib * 8
            return data_start

    # 备选：搜索 N-S 段头
    ns_pos = data.find(b"N-S")
    if ns_pos >= 4:
        seg_start = ns_pos - 4
        n_calib = struct.unpack_from("<I", data, seg_start + 32)[0]
        if n_calib > 0 and n_calib < 50:
            data_start = seg_start + 36 + n_calib * 8
            return data_start

    # 回退：使用 0x322C（常见偏移）
    return 0x322C


def find_first_valid_frame(evt_data: EvtData) -> int:
    """找到第一个持续有效的帧索引（跳过前导零/预触发数据）。

    返回持续非零区域开始的帧索引。
    """
    zero_mask = (
        (evt_data.ew == 0) & (evt_data.ns == 0) & (evt_data.ud == 0)
    )
    # 找连续 10 帧以上非零的起始位置
    for i in range(len(zero_mask) - 10):
        if not zero_mask[i:i + 10].any():
            return i
    return 0


def get_component_array(evt_data: EvtData, component: str) -> np.ndarray:
    """按名称获取分量数据。

    Parameters
    ----------
    evt_data : EvtData
    component : str
        "EW", "NS", 或 "UD"

    Returns
    -------
    np.ndarray
    """
    mapping = {"EW": evt_data.ew, "NS": evt_data.ns, "UD": evt_data.ud}
    if component not in mapping:
        raise ValueError(f"未知分量名: {component}，可选: EW, NS, UD")
    return mapping[component]