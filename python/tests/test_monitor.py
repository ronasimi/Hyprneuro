"""Deterministic bounded proc/sysfs fixtures; no models, services or network."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hyprneuro.monitor import Monitor
from hyprneuro.event_stream import ResourceAlerts


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tick = 0
        self.wall = 100
        self.monitor = Monitor(proc_root=self.root / "proc", sys_root=self.root / "sys",
            clock=lambda: self.tick, wall_clock=lambda: self.wall,
            statvfs=lambda _: SimpleNamespace(f_blocks=100, f_bavail=25))

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def cpu(self, user=100, idle=100, core="cpu0"):
        self.put("proc/stat", f"cpu {user} 0 0 {idle} 0 0 0 0 900 900\n"
                             f"{core} {user} 0 0 {idle} 0 0 0 0 900 900\n")

    def disk(self, read=10, written=20, name="sda"):
        self.put("proc/diskstats", f"8 0 {name} 1 0 {read} 0 2 0 {written} 0 3 0 0\n")

    def test_missing_sources_are_unknown_not_zero_and_recover(self):
        first = self.monitor.sample()
        self.assertEqual(first["cpu_percent"], {})
        self.assertEqual(first["memory_kib"], {})
        self.assertNotIn("memory_used_estimate_kib", first)
        self.assertNotIn("swap_used_kib", first)
        self.assertEqual(first["availability"]["cpu_percent"], "unavailable")
        self.cpu()
        self.disk()
        self.put("proc/meminfo", "MemTotal: 1000 kB\nMemAvailable: 250 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
        second = self.monitor.sample()
        self.assertEqual(second["availability"]["cpu_percent"], "warming_up")
        self.assertEqual(second["memory_used_estimate_kib"], 750)
        self.assertEqual(second["swap_used_kib"], 0)  # Real zero is distinct.
        self.assertIsNone(second["disk_io"]["sda"]["read_bytes_per_second"])
        json.dumps(second, allow_nan=False)

    def test_cpu_frequency_guest_exclusion_hotplug_reset_and_lost_source(self):
        self.cpu()
        self.put("sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "2400000\n")
        self.monitor.sample()
        self.cpu(user=125, idle=175)
        self.tick = 2
        snap = self.monitor.sample()
        self.assertEqual(snap["cpu_percent"], {"cpu": 25, "cpu0": 25})
        self.assertEqual(snap["cpu_frequency_khz"], {"cpu0": 2400000})
        for invalid in ("invalid", "-1", "0"):
            self.put("sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", invalid)
            self.assertEqual(self.monitor.sample()["cpu_frequency_khz"], {})
        self.cpu(user=150, idle=200, core="cpu1")
        snap = self.monitor.sample()
        self.assertNotIn("cpu0", snap["cpu_percent"])
        self.assertNotIn("cpu1", snap["cpu_percent"])
        self.assertEqual(snap["cpu_frequency_khz"], {})
        self.cpu(user=1, idle=1)
        self.assertEqual(self.monitor.sample()["cpu_percent"], {})
        (self.root / "proc/stat").unlink()
        self.monitor.sample()
        self.cpu(user=200, idle=200)
        self.assertEqual(self.monitor.sample()["cpu_percent"], {})
        self.cpu(user=200, idle=210)
        self.assertEqual(self.monitor.sample()["cpu_percent"]["cpu"], 0)

    def test_cpu_component_reset_even_when_total_increases(self):
        self.cpu(user=100, idle=100)
        self.monitor.sample()
        self.cpu(user=50, idle=200)
        self.assertEqual(self.monitor.sample()["cpu_percent"], {})
        self.cpu(user=60, idle=210)
        self.assertEqual(self.monitor.sample()["cpu_percent"]["cpu"], 50)

    def test_disk_monotonic_time_reset_and_hotplug(self):
        self.disk()
        self.monitor.sample()
        self.tick, self.wall = 2, -100  # Wall-clock changes do not affect rates.
        self.disk(12, 24)
        snap = self.monitor.sample()["disk_io"]["sda"]
        self.assertEqual(snap["read_bytes_per_second"], 512)
        self.assertEqual(snap["write_bytes_per_second"], 1024)
        self.assertEqual(snap["in_flight"], 3)
        self.disk(1, 1)
        self.tick = 3
        self.assertIsNone(self.monitor.sample()["disk_io"]["sda"]["read_bytes_per_second"])
        self.disk(2, 2)
        self.tick = 4
        self.assertEqual(self.monitor.sample()["disk_io"]["sda"]["read_bytes_per_second"], 512)
        self.put("proc/diskstats", "malformed\n")
        self.monitor.sample()
        self.disk(100, 100)
        self.tick = 5
        self.assertIsNone(self.monitor.sample()["disk_io"]["sda"]["read_bytes_per_second"])
        self.disk(101, 101)
        self.assertIsNone(self.monitor.sample()["disk_io"]["sda"]["read_bytes_per_second"])

    def test_malformed_values_do_not_suppress_independent_sources(self):
        self.put("proc/stat", "cpu 1 bad 3 4 5\ncpu0 -1 2 3 4 5\ncpu1 1 2\n")
        self.put("proc/meminfo", "MemTotal: bad kB\nMemAvailable: 10 kB\nSwapTotal: 8 kB\nSwapFree: 9 kB\n")
        self.put("proc/diskstats", "8 0 bad 1 0 nope 0 2 0 20 0 0 0 0\n")
        self.put("proc/pressure/cpu", "some avg10=nan avg60=0 avg300=0 total=0")
        self.put("proc/pressure/io", "some avg10=1.25 avg60=0 avg300=0 total=100\n")
        self.put("sys/class/net/test0/operstate", "up\n")
        self.put("sys/class/net/test0/statistics/rx_bytes", "0\n")
        self.put("sys/class/net/test0/statistics/tx_bytes", "garbage\n")
        self.put("sys/class/net/test0/statistics/rx_errors", "-1\n")
        snap = self.monitor.sample()
        self.assertEqual(snap["cpu_percent"], {})
        self.assertEqual(snap["disk_io"], {})
        self.assertNotIn("memory_used_estimate_kib", snap)
        self.assertNotIn("swap_used_kib", snap)
        self.assertEqual(set(snap["pressure"]), {"io"})
        self.assertEqual(snap["network"]["test0"], {"state": "up", "rx_bytes": 0})
        self.assertEqual(ResourceAlerts(duration=0).events(snap, now=0), [])

    def test_drm_not_vulkan_and_duplicate_sensor_names_do_not_overwrite(self):
        for hw, temp in (("hwmon0", "45000"), ("hwmon1", "55000")):
            self.put(f"sys/class/hwmon/{hw}/name", "coretemp\n")
            self.put(f"sys/class/hwmon/{hw}/temp1_input", temp)
        self.put("sys/class/hwmon/hwmon0/temp2_input", "invalid")
        self.put("sys/class/drm/card10/device/mem_info_vram_used", "0")
        self.put("sys/class/drm/card10/device/mem_info_gtt_used", "4096")
        self.put("sys/class/drm/card10/device/gpu_busy_percent", "101")
        self.put("sys/class/drm/card10-DP-1/device/gpu_busy_percent", "99")
        snap = self.monitor.sample()
        self.assertEqual(sorted(snap["temperatures_millicelsius"].values()), [45000, 55000])
        self.assertIn("coretemp/temp1_input", snap["temperatures_millicelsius"])
        self.assertEqual(list(snap["gpu"].values()), [{"mem_info_vram_used": 0, "mem_info_gtt_used": 4096}])
        self.assertIn("not Vulkan allocations", snap["gpu_note"])
        self.assertNotIn("vulkan", snap)
        self.assertNotIn("kv_cache", snap)

    def test_read_enumeration_sensor_interface_and_sampling_bounds(self):
        for i in range(70):
            self.put(f"sys/class/net/test{i}/operstate", "up")
            self.put(f"sys/class/hwmon/hwmon0/temp{i}_input", "42000")
        self.put("sys/class/hwmon/hwmon0/name", "sensor")
        snap = self.monitor.sample()
        self.assertEqual(len(snap["network"]), 64)
        self.assertEqual(len(snap["temperatures_millicelsius"]), 64)
        path = self.put("proc/large", "x" * (self.monitor.MAX_READ + 1))
        self.assertIsNone(self.monitor._read(path, self.monitor.MAX_READ))
        self.monitor.MAX_ENTRIES = 3
        self.assertEqual(len(self.monitor._entries(self.root / "sys/class/net")), 3)
        for value in (0, -.1, .1, 3601, float("inf"), float("nan")):
            with self.subTest(interval=value), self.assertRaises(ValueError):
                Monitor(interval=value)

    def test_cpu_disk_gpu_and_model_count_caps(self):
        self.monitor.MAX_CPUS = 2
        self.monitor.MAX_DISKS = 2
        self.monitor.MAX_GPUS = 2
        self.put("proc/stat", "cpu 1 2 3 4 5\n" + "".join(
            f"cpu{i} 1 2 3 4 5\n" for i in range(5)))
        self.put("proc/diskstats", "".join(
            f"8 0 disk{i} 1 0 10 0 2 0 20 0 0 0 0\n" for i in range(5)))
        for i in range(5):
            self.put(f"sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq", "1000")
            self.put(f"sys/class/drm/card{i}/device/gpu_busy_percent", "0")
        snap = self.monitor.sample()
        self.assertEqual(len(snap["cpu_frequency_khz"]), 2)
        self.assertEqual(len(snap["disk_io"]), 2)
        self.assertEqual(len(snap["gpu"]), 2)
        m = Monitor(model_processes={f"role{i}": {} for i in range(20)})
        self.assertEqual(len(m.model_processes), 8)

    def test_lost_optional_sources_do_not_retain_stale_readings(self):
        network = self.put("sys/class/net/test0/operstate", "up")
        gpu = self.put("sys/class/drm/card0/device/gpu_busy_percent", "50")
        mem = self.put("proc/meminfo", "MemTotal: 100 kB\nMemAvailable: 10 kB\n")
        before = self.monitor.sample()
        for path in (network, gpu, mem):
            path.unlink()
        after = self.monitor.sample()
        for key in ("network", "gpu", "memory_kib"):
            self.assertTrue(before[key])
            self.assertEqual(after[key], {})
            self.assertEqual(after["availability"][key], "unavailable")
        self.assertNotIn("memory_used_estimate_kib", after)

    def process_stat(self, start=50):
        return "42 (name with ) parens) " + " ".join(["S"] + ["0"] * 18 + [str(start)])

    def test_explicit_process_identity_residency_not_model_allocation(self):
        self.monitor.model_processes = {"text": {"pid": 42, "start_ticks": "50"}}
        self.put("proc/42/stat", self.process_stat())
        self.put("proc/42/status", "Name: not-collected\nVmRSS: 1024 kB\nVmSwap: 0 kB\n")
        snap = self.monitor.sample()["model_processes"]["text"]
        self.assertEqual(snap, {"available": True, "pid": 42, "start_ticks": "50", "rss_kib": 1024, "swap_kib": 0})
        self.put("proc/42/stat", self.process_stat(start=51))
        self.assertEqual(self.monitor.sample()["model_processes"]["text"], {"available": False})
        self.put("proc/42/stat", self.process_stat())
        self.put("proc/42/status", "VmRSS: malformed\n")
        self.assertEqual(self.monitor.sample()["model_processes"]["text"], {"available": False})
        self.put("proc/42/status", "VmRSS: 8 kB\n")
        original = self.monitor._read
        def reused(path, limit=4096):
            result = original(path, limit)
            if path.name == "status":
                self.put("proc/42/stat", self.process_stat(start=51))
            return result
        with patch.object(self.monitor, "_read", side_effect=reused):
            self.assertFalse(self.monitor.sample()["model_processes"]["text"]["available"])
        (self.root / "proc/42/stat").unlink()
        self.assertFalse(self.monitor.sample()["model_processes"]["text"]["available"])

    def test_no_external_operations(self):
        with patch("subprocess.Popen", side_effect=AssertionError("subprocess")), \
             patch("socket.socket", side_effect=AssertionError("network")):
            self.monitor.sample()


class MonitorLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_failure_then_recovery_cancellation_retains_latest(self):
        with tempfile.TemporaryDirectory() as root:
            monitor = Monitor(interval=.25, proc_root=root, sys_root=root,
                              statvfs=lambda _: (_ for _ in ()).throw(OSError()))
            seen = []
            async def deliver(snapshot):
                seen.append(snapshot)
                if len(seen) == 1:
                    raise OSError("synthetic delivery failure")
            real_sleep = asyncio.sleep
            async def fast_sleep(_):
                await real_sleep(0)
            with patch("hyprneuro.monitor.asyncio.sleep", fast_sleep):
                task = asyncio.create_task(monitor.run(deliver))
                try:
                    for _ in range(100):
                        if len(seen) >= 2:
                            break
                        await real_sleep(0)
                    self.assertGreaterEqual(len(seen), 2)
                finally:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
            self.assertEqual(monitor.delivery_failures, 1)
            self.assertIs(monitor.latest, seen[-1])
            self.assertNotIn("error", monitor.latest)
