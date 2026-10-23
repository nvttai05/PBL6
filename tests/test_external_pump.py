"""External pump reports are user annotations; no GPIO/I2C calls in these tests."""
import csv
import hashlib
import json
import subprocess
import sys
import time
import pytest
from robonose.cli import parser
from robonose.config import load
from robonose.session import Context, Acquisition
from robonose.readers import SimReader
from robonose.state import StateMachine
from robonose.writer import RunWriter
from scripts.verify_interactive import GUARD
from tests.test_session import Process, csv_rows

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("ending", ["quit","abort","eof","fatal"])
def test_hardware_cli_disabled_never_imports_or_opens_gpio(tmp_path, ending):
    cfg = tmp_path/"enabled.toml"
    # --pump-disabled must win even over an enabled, unconfirmed file.
    cfg.write_text("[pump]\nenabled=true\nconfirmed=false\n")
    patch = """
from robonose.readers import SimReader
import robonose.session as session
class FakeHardware(SimReader):
    def read(self, *args):
        if ENDING == 'fatal' and self.index >= 3:
            raise OSError('mock sensor lost')
        return super().read(*args)
session.HardwareReader = FakeHardware
session.analyze = lambda path: None
"""
    guarded = GUARD.replace("raise SystemExit(main())",patch.replace("ENDING",repr(ending))+"\nraise SystemExit(main())")
    commands = {"quit":"start\nquit\n","abort":"start\nabort\nquit\n","eof":"start\n","fatal":""}
    argv=[sys.executable,"-c",guarded,"collect","--hardware","--pump-disabled",
          "--config",str(cfg),"--sample-hz","20","--baseline","30","--output",str(tmp_path/"out")]
    if ending=="fatal":
        with subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as proc:
            proc.stdin.write("start\n");proc.stdin.flush()
            proc.wait(timeout=20) # stdin stays open until the mock sensor disappears
            stdout,stderr=proc.communicate(timeout=5)
            result=type("Result",(),{"returncode":proc.returncode,"stdout":stdout,"stderr":stderr})()
    else:
        result=subprocess.run(argv,input=commands[ending],capture_output=True,text=True,timeout=20)
    output=tmp_path/"out"
    assert result.returncode == (1 if ending=="fatal" else 0), result.stdout+result.stderr
    assert "Hardware import forbidden" not in result.stdout+result.stderr
    meta = next(json.loads(p.read_text()) for p in output.glob("exploration/*/*/metadata.json")
                if json.loads(p.read_text())["kind"]=="collect")
    assert meta["status"]==("ERROR" if ending=="fatal" else "ABORTED")
    assert meta["config"]["pump"]["enabled"] is False
    assert meta["applied"]["pump"]["initial_command"]=="DISABLED"

def test_doctor_disabled_no_gpio_with_enabled_config(tmp_path):
    cfg=tmp_path/"enabled.toml";cfg.write_text("[pump]\nenabled=true\nconfirmed=false\n")
    result=subprocess.run([sys.executable,"-c",GUARD,"doctor","--pump-disabled","--config",str(cfg)],
                          capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report["hardware_opened"] is False and report["pump_config"]["enabled"] is False

def test_external_reports_keep_manual_state_across_abort_and_next(tmp_path):
    app=Process(tmp_path,["--external-pump-state","not-used"])
    try:
        app.wait("MONITOR |")
        app.send("external-pump on bật nguồn riêng")
        app.send("mark đổi ống, mở nắp")
        app.send("start");app.wait("Pha BASELINE")
        time.sleep(.15)
        app.send("abort");app.wait("Đặt tên:")
        app.send("skip");app.send("skip");app.wait("next để thu lượt mới")
        app.send("next");app.wait("Lượt mới:",count=2)
        time.sleep(.1)
        app.send("external-pump off tắt nguồn riêng")
        time.sleep(.15)
        app.send("quit")
        assert app.p.wait(timeout=40)==0,app.text()
        runs=app.runs()
        assert len(runs)==2
        first=next((p,m) for p,m in runs if m["external_pump"]["initial_state"]=="not-used")
        second=next((p,m) for p,m in runs if m["external_pump"]["initial_state"]=="on")
        assert first[1]["external_pump"]["latest_state"]=="on" # abort did not switch external power
        assert second[1]["external_pump"]["latest_state"]=="off"
        assert all(r["pump_command"]=="DISABLED" for p,m in runs for r in csv_rows(p/"raw.csv"))
        assert any(r["external_pump_state"]=="on" for r in csv_rows(first[0]/"raw.csv"))
        assert any(r["external_pump_state"]=="off" for r in csv_rows(second[0]/"raw.csv"))
        event=next(json.loads(e["details_json"]) for e in csv_rows(first[0]/"events.csv") if e["event"]=="external_pump_report")
        assert event["note"]=="bật nguồn riêng" and event["physical_feedback"] is None and not event["gpio_command_sent"]
        marker=next(e for e in csv_rows(first[0]/"events.csv") if e["event"]=="marker")
        assert json.loads(marker["details_json"])["text"]=="đổi ống, mở nắp"
        assert "không nói trạng thái bơm ngoài" in app.text()
    finally:app.close()

def test_external_snapshot_and_deadline_do_not_change_inflight_sample():
    import threading
    entered,release=threading.Event(),threading.Event()
    class Slow(SimReader):
        def read(self,*a):
            entered.set();assert release.wait(2)
            return super().read(*a)
    reader=Slow(load());now=time.monotonic()
    original=Context(None,"BASELINE",now,"BASELINE","DISABLED",now+.2,"on","user_reported")
    acq=Acquisition(reader,20,now,original);acq.thread.start()
    assert entered.wait(2)
    acq.set_context(Context(None,"BASELINE",now,"BASELINE","DISABLED",now+.2,"off","user_reported"))
    release.set()
    kind,row,ctx=acq.items.get(timeout=2)
    acq.stop.set();acq.thread.join(2)
    assert ctx.external_pump_state=="on"
    late=original.at(now+2)
    assert late.phase=="WAIT_EXPOSURE" and late.since==now+.2 and late.external_pump_state=="on"

@pytest.mark.parametrize("failure",["sync","raw_close"])
def test_close_failure_keeps_data_and_error_metadata(tmp_path,monkeypatch,failure):
    cfg=load();w=RunWriter(tmp_path,"sim",cfg,{})
    from robonose.schema import blank_sample
    row=blank_sample();row.update(timestamp="2026-10-03T00:00:00+07:00",elapsed_s=0,phase="MONITOR")
    w.row(row);w.event("marker",w.start,"MONITOR",w.start,{"text":"đã ghi"})
    if failure=="sync":
        monkeypatch.setattr(w,"sync",lambda **kw: (_ for _ in ()).throw(OSError("mock fsync failure")))
    else:
        original=w.raw_file
        class Closing:
            def __getattr__(self,key):return getattr(original,key)
            def close(self):
                original.close()
                raise OSError("mock close failure")
        w.raw_file=Closing()
    with pytest.raises(RuntimeError,match="Đóng lượt lỗi"):
        w.finish(StateMachine(w.start,{}),"ABORTED",time.monotonic(),"test")
    meta=json.loads((w.path/"metadata.json").read_text())
    assert meta["status"]=="ERROR" and w.closed
    assert len(csv_rows(w.path/"raw.csv"))==1
    assert csv_rows(w.path/"events.csv")[0]["event"]=="marker"


def test_session_close_error_still_analyzes_retained_files(tmp_path):
    from robonose.session import Session
    class BrokenCloseSession(Session):
        def new_run(self):
            super().new_run()
            original=self.run.raw_file
            class Closing:
                def __getattr__(self,key):return getattr(original,key)
                def close(self):
                    original.close()
                    raise OSError("mock raw close error")
            self.run.raw_file=Closing()
        def auto(self,now):
            if self.run and self.reader.index>=3:
                self.command("abort")
    cfg=load();cfg["sample_hz"]=30
    args=parser().parse_args(["collect","--sim","--pump-disabled","--auto","--output",str(tmp_path)])
    session=BrokenCloseSession(args,cfg)
    assert session.run_session()==1
    path=session.finishing.path
    assert json.loads((path/"metadata.json").read_text())["status"]=="ERROR"
    assert len(csv_rows(path/"raw.csv"))>=2
    assert (path/"events.csv").stat().st_size>0
    assert json.loads((path/"summary.json").read_text())["status"]=="ERROR"
    for file in ("signals.png","normalized.png"):
        assert (path/file).read_bytes().startswith(b"\x89PNG")

def test_monitor_hardware_disabled_and_offline_analyze_guard(tmp_path):
    patch = """
from robonose.readers import SimReader
import robonose.session as session
session.HardwareReader = SimReader
"""
    guarded=GUARD.replace("raise SystemExit(main())",patch+"\nraise SystemExit(main())")
    result=subprocess.run([sys.executable,"-c",guarded,"monitor","--hardware","--pump-disabled",
        "--output",str(tmp_path)],input="",capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    meta_path=next(tmp_path.glob("exploration/*/*/metadata.json"))
    meta=json.loads(meta_path.read_text())
    assert meta["kind"]=="monitor" and meta["status"]=="COMPLETE"
    assert meta["external_pump"]["initial_state"]=="unknown"
    files=("raw.csv","events.csv","metadata.json")
    hashes={f:hashlib.sha256((meta_path.parent/f).read_bytes()).hexdigest() for f in files}
    offline=subprocess.run([sys.executable,"-c",GUARD,"analyze",str(meta_path.parent)],
                           capture_output=True,text=True,timeout=30)
    assert offline.returncode==0,offline.stdout+offline.stderr
    assert all(hashlib.sha256((meta_path.parent/f).read_bytes()).hexdigest()==h for f,h in hashes.items())
    for file in ("signals.png","normalized.png"):
        assert (meta_path.parent/file).read_bytes().startswith(b"\x89PNG")
