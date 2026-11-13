"""Bounded passive Linux counters; no subprocesses, inference or service probes.

Missing readings are omitted (rates are None until a valid delta). proc_root,
sys_root and clocks are injectable for deterministic tests. See the P12 adapter
contract before wiring this sampler into another lifecycle.
"""
import asyncio
from itertools import islice
import math
import os
from pathlib import Path
import time


class Monitor:
    MAX_CPUS = 256
    MAX_DISKS = 128
    MAX_INTERFACES = 64
    MAX_SENSORS = 64
    MAX_HWMON = 32
    MAX_GPUS = 16
    MAX_MODELS = 8
    MAX_ENTRIES = 512
    MAX_READ = 262144

    def __init__(self, interval=2, *, proc_root="/proc", sys_root="/sys",
                 clock=time.monotonic, wall_clock=time.time, statvfs=os.statvfs,
                 model_processes=None):
        if not isinstance(interval, (int, float)) or not math.isfinite(interval) or not .25 <= interval <= 3600:
            raise ValueError("interval must be 0.25..3600 seconds")
        self.interval = interval
        self.proc = Path(proc_root)
        self.sys = Path(sys_root)
        self.clock, self.wall_clock, self.statvfs = clock, wall_clock, statvfs
        # Explicit role -> {pid, start_ticks}; no process discovery/argv/maps read.
        self.model_processes = dict(islice((model_processes or {}).items(), self.MAX_MODELS))
        self.latest = {}
        self.delivery_failures = 0
        self.previous = {}
        self.previous_disks = {}
        self.previous_time = None

    def _read(self, path, limit=4096):
        try:
            with path.open("rb") as stream:
                data = stream.read(limit + 1)
            if len(data) <= limit:
                return data.decode("ascii").strip()
        except (OSError, UnicodeError):
            pass
        return None

    def _integer(self, path):
        try:
            value = int(self._read(path, 128))
            return value if value >= 0 else None
        except (TypeError, ValueError):
            return None

    def _entries(self, path):
        # Bound enumeration itself, not just the returned list; never recurse.
        try:
            with os.scandir(path) as entries:
                return [Path(entry.path) for entry in islice(entries, self.MAX_ENTRIES)]
        except OSError:
            return []

    def sample(self):
        now = self.clock()
        elapsed = now - self.previous_time if self.previous_time is not None else 0
        out = {"time": self.wall_clock(), "cpu_percent": {}, "cpu_frequency_khz": {},
               "memory_kib": {}, "temperatures_millicelsius": {}, "pressure": {},
               "gpu": {}, "disk_io": {}, "disk_used_percent": {}, "network": {},
               "model_processes": {}}
        cpu = {}
        for line in (self._read(self.proc / "stat", self.MAX_READ) or "").splitlines():
            parts = line.split()
            if not parts or not (parts[0] == "cpu" or parts[0].startswith("cpu") and parts[0][3:].isdigit()):
                continue
            if len(cpu) >= self.MAX_CPUS + 1:
                break
            try:
                # guest/guest_nice are already included in user/nice.
                vals = list(map(int, parts[1:9]))
                if len(vals) < 5 or min(vals) < 0:
                    continue
                total, idle = sum(vals), vals[3] + vals[4]
                cpu[parts[0]] = vals
                old = self.previous.get(parts[0])
                if old is not None:
                    delta, idle_delta = total - sum(old), idle - old[3] - old[4]
                    if (len(vals) == len(old) and all(v >= p for v, p in zip(vals, old))
                            and delta > 0 and 0 <= idle_delta <= delta):
                        out["cpu_percent"][parts[0]] = 100 * (1 - idle_delta / delta)
            except ValueError:
                continue
        self.previous = cpu  # Gone/unreadable CPUs lose their baseline.
        for name in cpu:
            if name == "cpu":
                continue
            freq = self._integer(self.sys / "devices/system/cpu" / name / "cpufreq/scaling_cur_freq")
            if freq is not None and freq > 0:
                out["cpu_frequency_khz"][name] = freq
        for line in (self._read(self.proc / "meminfo", 16384) or "").splitlines():
            key, _, rest = line.partition(":")
            if key not in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                continue
            try:
                value, unit = rest.split()
                if int(value) >= 0 and unit == "kB":
                    out["memory_kib"][key] = int(value)
            except ValueError:
                continue
        memory = out["memory_kib"]
        for total, free, target in (("MemTotal", "MemAvailable", "memory_used_estimate_kib"),
                                     ("SwapTotal", "SwapFree", "swap_used_kib")):
            if total in memory and free in memory and memory[free] <= memory[total]:
                out[target] = memory[total] - memory[free]
        for name in ("cpu", "memory", "io"):
            text = self._read(self.proc / "pressure" / name)
            if text and self._valid_pressure(text):
                out["pressure"][name] = text
        disks = {}
        for line in (self._read(self.proc / "diskstats", self.MAX_READ) or "").splitlines():
            fields = line.split()
            if len(fields) < 14:
                continue
            if len(disks) >= self.MAX_DISKS:
                break
            try:
                name = fields[2]
                read, written, in_flight = (int(fields[i]) for i in (5, 9, 11))
                if min(read, written, in_flight) < 0:
                    continue
                read, written = read * 512, written * 512
                disks[name] = (read, written)
                old = self.previous_disks.get(name)
                valid = old is not None and elapsed > 0 and read >= old[0] and written >= old[1]
                out["disk_io"][name] = {"read_bytes": read, "written_bytes": written,
                    "in_flight": in_flight,
                    "read_bytes_per_second": (read-old[0])/elapsed if valid else None,
                    "write_bytes_per_second": (written-old[1])/elapsed if valid else None}
            except ValueError:
                continue
        self.previous_disks, self.previous_time = disks, now
        try:
            fs = self.statvfs("/")
            if fs.f_blocks > 0 and 0 <= fs.f_bavail <= fs.f_blocks:
                out["disk_used_percent"]["/"] = 100 * (1 - fs.f_bavail / fs.f_blocks)
        except OSError:
            pass
        for interface in self._entries(self.sys / "class/net")[:self.MAX_INTERFACES]:
            counters = {}
            state = self._read(interface / "operstate", 128)
            if state in ("unknown", "notpresent", "down", "lowerlayerdown", "testing", "dormant", "up"):
                counters["state"] = state
            for key in ("rx_bytes", "tx_bytes", "rx_errors", "tx_errors"):
                value = self._integer(interface / "statistics" / key)
                if value is not None:
                    counters[key] = value
            if counters:
                out["network"][interface.name] = counters
        sensors = 0
        for hw in self._entries(self.sys / "class/hwmon")[:self.MAX_HWMON]:
            if sensors >= self.MAX_SENSORS:
                break
            name = self._read(hw / "name", 128)
            if not name:
                continue
            for path in self._entries(hw):
                if not (path.name.startswith("temp") and path.name[4:-6].isdigit() and path.name.endswith("_input")):
                    continue
                if sensors >= self.MAX_SENSORS:
                    break
                sensors += 1  # Bad/missing sensors consume the read budget too.
                try:
                    value = int(self._read(path, 128))
                    if -273150 <= value <= 250000:
                        key = name + "/" + path.name
                        if key in out["temperatures_millicelsius"]:
                            key = name + "/" + hw.name + "/" + path.name
                        out["temperatures_millicelsius"][key] = value
                except (TypeError, ValueError):
                    pass
        cards = (p for p in self._entries(self.sys / "class/drm")
                 if p.name.startswith("card") and p.name[4:].isdigit())
        for card in islice(cards, self.MAX_GPUS):
            counters = {}
            for key in ("mem_info_vram_used", "mem_info_gtt_used", "gpu_busy_percent"):
                value = self._integer(card / "device" / key)
                if value is not None and (key != "gpu_busy_percent" or value <= 100):
                    counters[key] = value
            if counters:
                out["gpu"][str(card / "device")] = counters
        out["gpu_note"] = ("Global DRM driver memory counters (bytes), not Vulkan allocations or per-model memory. "
                           "VRAM and GTT are separate accounting domains; backing/overlap depends on hardware. "
                           "No KV/cache occupancy is inferred.")
        for role, identity in islice(self.model_processes.items(), self.MAX_MODELS):
            out["model_processes"][role] = self._process(identity)
        # Additive metadata: legacy dictionaries/units are retained. Empty means unknown,
        # except disk rates and first CPU samples which require a valid baseline.
        out["availability"] = {key: "available" if out[key] else "unavailable" for key in
            ("cpu_frequency_khz", "memory_kib", "pressure", "gpu", "disk_io",
             "disk_used_percent", "network", "temperatures_millicelsius")}
        out["availability"]["cpu_percent"] = "available" if out["cpu_percent"] else "warming_up" if cpu else "unavailable"
        out["availability"]["model_processes"] = ("available" if any(
            p.get("available") for p in out["model_processes"].values()) else "unavailable")
        self.latest = out
        return out

    @staticmethod
    def _valid_pressure(text):
        try:
            for line in text.splitlines():
                kind, *fields = line.split()
                values = dict(field.split("=", 1) for field in fields)
                if kind not in ("some", "full"):
                    return False
                if not all(0 <= float(values[k]) <= 100 for k in ("avg10", "avg60", "avg300")):
                    return False
                if int(values["total"]) < 0:
                    return False
            return True
        except (ValueError, KeyError):
            return False

    def _process(self, identity):
        missing = {"available": False}
        if not isinstance(identity, dict):
            return missing
        pid, start = identity.get("pid"), identity.get("start_ticks")
        if type(pid) is not int or pid <= 0 or not str(start).isdigit():
            return missing
        path = self.proc / str(pid)
        def same_process():
            text = self._read(path / "stat", 4096)
            try:
                return text.rsplit(")", 1)[1].split()[19] == str(start)
            except (AttributeError, IndexError):
                return False
        if not same_process():
            return missing
        status = {}
        for line in (self._read(path / "status", 16384) or "").splitlines():
            key, _, rest = line.partition(":")
            if key in ("VmRSS", "VmSwap"):
                try:
                    value, unit = rest.split()
                    if int(value) >= 0 and unit == "kB":
                        status[{"VmRSS": "rss_kib", "VmSwap": "swap_kib"}[key]] = int(value)
                except ValueError:
                    pass
        if not status or not same_process():  # PID reuse during the read is unknown too.
            return missing
        return {"available": True, "pid": pid, "start_ticks": str(start), **status}

    async def run(self, on_sample=None):
        while True:
            snapshot = self.sample()
            if on_sample is not None:
                try:
                    await on_sample(snapshot)
                except (OSError, ValueError, KeyError):
                    # A delivery failure must not erase good passive readings.
                    self.delivery_failures += 1
            await asyncio.sleep(self.interval)
