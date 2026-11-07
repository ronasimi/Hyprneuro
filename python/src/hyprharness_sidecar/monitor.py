"""Low overhead passive Linux telemetry; no sudo, scans, perf or polling subprocesses."""
import asyncio
from pathlib import Path
import time

class Monitor:
    def __init__(self, interval=2):
        self.interval=interval;self.latest={};self.previous=None;self.previous_disks={};self.previous_time=None

    def sample(self):
        out={"time":time.time(),"temperatures_millicelsius":{},"pressure":{},"gpu":{}}
        cpu={}
        for line in Path("/proc/stat").read_text().splitlines():
            parts=line.split()
            if parts and (parts[0]=="cpu" or parts[0].startswith("cpu") and parts[0][3:].isdigit()):
                # guest fields are already included in user/nice.
                vals=list(map(int,parts[1:9]));cpu[parts[0]]=(sum(vals),vals[3]+vals[4])
        out["cpu_percent"]={}
        if self.previous:
            for name,(total,idle) in cpu.items():
                old=self.previous.get(name,(total,idle));delta=total-old[0]
                out["cpu_percent"][name]=100*(1-(idle-old[1])/delta) if delta>0 else 0
        self.previous=cpu
        out["memory_kib"]={k:int(v.split()[0]) for k,v in (line.split(":",1) for line in Path("/proc/meminfo").read_text().splitlines())
                           if k in ("MemTotal","MemAvailable","SwapTotal","SwapFree")}
        for p in Path("/proc/pressure").glob("*"):
            try:out["pressure"][p.name]=p.read_text().strip()
            except OSError:pass
        memory=out["memory_kib"]
        out["memory_used_estimate_kib"]=memory["MemTotal"]-memory["MemAvailable"]
        out["swap_used_kib"]=memory["SwapTotal"]-memory["SwapFree"]
        elapsed=out["time"]-self.previous_time if self.previous_time else 0
        disks={};out["disk_io"]={}
        for line in Path("/proc/diskstats").read_text().splitlines():
            fields=line.split()
            if len(fields)<14:continue
            name=fields[2];read=int(fields[5])*512;written=int(fields[9])*512;disks[name]=(read,written)
            prev=self.previous_disks.get(name,(read,written))
            out["disk_io"][name]={"read_bytes":read,"written_bytes":written,"in_flight":int(fields[11]),
                "read_bytes_per_second":max(0,read-prev[0])/elapsed if elapsed>0 else None,
                "write_bytes_per_second":max(0,written-prev[1])/elapsed if elapsed>0 else None}
        self.previous_disks=disks;self.previous_time=out["time"]
        out["network"]={}
        for interface in Path("/sys/class/net").iterdir():
            try:out["network"][interface.name]={"state":(interface/"operstate").read_text().strip(),
                **{key:int((interface/"statistics"/key).read_text()) for key in ("rx_bytes","tx_bytes","rx_errors","tx_errors")}}
            except (OSError,ValueError):pass
        for hw in Path("/sys/class/hwmon").glob("hwmon*"):
            for p in hw.glob("temp*_input"):
                try:
                    name=(hw/"name").read_text().strip()
                    out["temperatures_millicelsius"][name+"/"+p.name]=int(p.read_text())
                except (OSError,ValueError):pass
        for dev in Path("/sys/class/drm").glob("card[0-9]*/device"):
            counters={}
            for key in ("mem_info_vram_used","mem_info_gtt_used","gpu_busy_percent"):
                try:counters[key]=int((dev/key).read_text())
                except (OSError,ValueError):pass
            if counters:out["gpu"][str(dev)]=counters
        out["gpu_note"]="Global DRM VRAM and GTT are separate; both use system RAM on this iGPU."
        self.latest=out
        return out

    # TODO: feed event_stream.EventIntake via snapshots rather than starting
    # another resource poller. Keep existing telemetry lightweight.
    async def run(self):
        while True:
            try:self.sample()
            except OSError as e:self.latest={"error":str(e),"time":time.time()}
            await asyncio.sleep(self.interval)
